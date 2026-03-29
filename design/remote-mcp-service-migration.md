# SocialHub Remote Service Migration Plan

## 1. Document Goal

This document defines how `Socialhub-CLI` should evolve from:

- local CLI execution
- local Claude Desktop MCP bridge

to a centralized service model based on:

- remote application services
- remote MCP for Claude Desktop
- remote API clients for CLI

The goal is not only to describe the architecture direction. It is to provide a migration plan that is concrete enough to guide implementation, rollout, and verification.

This document covers:

- the current system shape and its limitations
- the target architecture and design principles
- proposed repository and service boundaries
- directory structure changes
- CLI / API / MCP interface design
- context, tenant, and auth handling
- caching, timeout, logging, and observability concerns
- deployment guidance
- migration phases, rollback strategy, and acceptance criteria

## 2. Current System

### 2.1 Current Entry Points

The repository already has working local entry points:

- CLI entry: [pyproject.toml](/C:/Users/86185/Socialhub-CLI/pyproject.toml)
  - `socialhub = "cli.main:cli"`
- MCP entry: [pyproject.toml](/C:/Users/86185/Socialhub-CLI/pyproject.toml)
  - `socialhub-mcp = "mcp_server.__main__:main"`
- Local Claude Desktop bridge: [run_claude_mcp.py](/C:/Users/86185/Socialhub-CLI/run_claude_mcp.py)
- MCP implementation: [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py)
- Analytics command implementation: [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py)

### 2.2 Current Effective Architecture

The current implementation mixes three layers:

1. Presentation and protocol layer
- CLI commands and Rich output
- Claude Desktop through MCP

2. Business logic layer
- `_get_mcp_overview`
- `_get_mcp_orders`
- `_get_mcp_products`
- other `_get_mcp_*` helpers

3. Data access layer
- `MCPClient`
- SSE / POST communication with the upstream analytics backend

### 2.3 Current Problems

The current model works locally, but it is not a good fit for multi-user, remotely managed, production-grade operation.

1. CLI, MCP, and analytics logic are tightly coupled
- [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) mixes argument parsing, result rendering, and query orchestration
- [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py) directly imports or depends on CLI-oriented logic

2. Tenant and user context are not truly request-scoped
- much of the logic depends on `config.mcp.*`
- `tenant_id` behaves more like static configuration than runtime context

3. Claude Desktop currently depends on a local process
- the user machine needs Python
- the user machine needs the repo or installed package
- local setup and version consistency are hard to control

4. Auth, audit, rate limiting, and caching are not centralized
- local mode cannot reliably enforce who can query what
- logs are fragmented on user machines
- slow queries are not centrally observable

5. Service boundaries are unclear
- the current structure is difficult to reuse for API, web, automation, and future workflow execution

## 3. Target Architecture

### 3.1 Overall Goal

Move the system to a model where:

- Claude Desktop connects through remote MCP
- CLI defaults to remote API access
- core analytics logic is centralized in shared services
- warehouse credentials stay on the server side
- auth, tenant isolation, audit logging, caching, and observability are centralized

### 3.2 Target Architecture Diagram

```text
+-------------------+         +----------------------+
| Claude Desktop    | ----->  | Remote MCP Gateway   |
+-------------------+         +----------------------+
                                      |
                                      v
+-------------------+         +----------------------+
| socialhub CLI     | ----->  | REST API Gateway     |
+-------------------+         +----------------------+
                                      |
                                      v
                           +--------------------------+
                           | SocialHub App Service    |
                           | - auth                   |
                           | - tenant resolution      |
                           | - analytics service      |
                           | - cache                  |
                           | - audit log              |
                           +--------------------------+
                                      |
                          +-----------+-----------+
                          |                       |
                          v                       v
                 +------------------+   +------------------+
                 | MCP/DB adapters  |   | Job/Cache layer  |
                 +------------------+   +------------------+
                          |
                          v
                 +----------------------+
                 | Snowflake / DWH /    |
                 | internal MCP backend |
                 +----------------------+
```

### 3.3 Core Principles

1. Request-scoped context first
- user, tenant, role, and trace information must be request-scoped

2. Protocol adapters must be separate from business logic
- MCP handlers must not own core analytics behavior
- CLI commands must not own core analytics behavior

3. One backend service domain
- CLI, Claude, and future web entry points should all depend on the same shared service layer

4. Local mode remains available, but becomes a development fallback
- production should prefer remote services

## 4. Recommended Directory Structure

### 4.1 Target Layout

```text
socialhub_core/
  context/
    request_context.py
    auth_context.py
  domain/
    analytics/
      models.py
      service.py
      validators.py
  infra/
    cache/
      redis_cache.py
    logging/
      audit_logger.py
    auth/
      token_verifier.py
    config/
      settings.py
  adapters/
    warehouse/
      analytics_repository.py
    mcp_backend/
      mcp_query_client.py

api_server/
  app.py
  routers/
    analytics.py
    health.py
    auth.py
  dependencies/
    context.py
    permissions.py

mcp_server/
  server.py
  handlers/
    analytics.py

cli/
  remote/
    client.py
    auth.py
```

### 4.2 What Moves Where

Keep in CLI:

- Typer argument definitions
- Rich rendering
- local export behavior

Move into shared service or repository:

- `_get_mcp_overview`
- `_get_mcp_customers`
- `_get_mcp_orders`
- `_get_mcp_products`
- `_get_mcp_retention`
- other core `_get_mcp_*` data retrieval logic

Move into repository specifically:

- direct SQL or MCP request assembly
- wrappers around `MCPClient`

## 5. Layer Responsibilities

### 5.1 Request Context

Every service entry point must receive a request context.

Example target file: `socialhub_core/context/request_context.py`

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RequestContext:
    request_id: str
    trace_id: str
    user_id: str
    tenant_id: str
    org_id: str | None = None
    roles: list[str] = field(default_factory=list)
    source: str = "api"  # api | mcp | cli
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_role(self, role: str) -> bool:
        return role in self.roles
```

### 5.2 Service Layer

The service layer is responsible for:

- business validation
- analytics semantics
- query orchestration
- tenant and permission checks
- response assembly

The service layer must not:

- render terminal output
- return Rich objects
- depend on CLI-only code

### 5.3 Repository Layer

The repository layer is responsible for:

- warehouse or MCP request assembly
- raw data retrieval
- result normalization into plain Python structures

The repository layer must not:

- generate business recommendations
- format user-facing terminal text
- perform presentation-layer work

### 5.4 CLI Layer

The CLI layer is responsible for:

- user-facing command arguments
- building query models
- calling the service layer
- rendering tables, markdown, and exports

### 5.5 MCP Layer

The MCP layer is responsible for:

- receiving MCP tool inputs
- mapping them to request context and query models
- calling the service layer
- returning MCP protocol responses

It must not own duplicated analytics logic.

### 5.6 API Layer

The API layer is responsible for:

- HTTP request parsing
- auth and dependency resolution
- request context construction
- calling shared services
- returning JSON responses

## 6. Delivery Model

### 6.1 API Service Responsibilities

The API service should support:

- CLI remote usage
- future web usage
- automation usage

Typical routes:

- `GET /health`
- `POST /api/analytics/overview`
- `POST /api/analytics/orders`
- `POST /api/analytics/customers`
- `POST /api/analytics/report`

### 6.2 MCP Service Responsibilities

The MCP service should support:

- Claude Desktop remote access
- tool schema exposure
- request translation from MCP tool args to query models

Typical guidance:

- MCP is the protocol adapter for Claude
- API is the transport used by CLI and web
- both must depend on the same service layer

## 7. Auth, Tenant Isolation, and Audit

### 7.1 Auth Model

Suggested server-side auth modes:

- local/dev auth for development
- bearer token auth for CLI
- OIDC or equivalent for platform users

### 7.2 Tenant Resolution

Tenant resolution must be request-scoped and server-side.

Sources may include:

- token claims
- user profile lookup
- gateway-injected metadata

### 7.3 Audit Requirements

At minimum, audit logs should capture:

- request ID
- trace ID
- user ID
- tenant ID
- route or tool name
- query type
- duration
- success or failure

## 8. Remote MCP Deployment Mode

### 8.1 MCP Service Role

The MCP service is not where analytics business logic should live.
It is where Claude-facing protocol adaptation should live.

### 8.2 API Service Role

The API service is where CLI and future web should connect.

### 8.3 Shared-Service Rule

Both API and MCP must call the same shared analytics service.

No new analytics logic should be duplicated in:

- MCP handlers
- API routers
- CLI commands

## 9. Configuration

### 9.1 Environment Variables

Example:

```env
API_HOST=0.0.0.0
API_PORT=8000
MCP_PORT=8090

REDIS_URL=redis://redis:6379/0

AUTH_MODE=oidc
OIDC_ISSUER=https://auth.company.com
OIDC_AUDIENCE=socialhub

BACKEND_MODE=mcp
MCP_SSE_URL=https://internal-backend/sse
MCP_POST_URL=https://internal-backend/message

DEFAULT_DATABASE=default
```

### 9.2 Settings Example

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "dev"
    log_level: str = "INFO"
    redis_url: str = "redis://localhost:6379/0"
    auth_mode: str = "dev"
    backend_mode: str = "mcp"
    mcp_sse_url: str
    mcp_post_url: str
    default_database: str = "default"

    class Config:
        env_file = ".env"
```

## 10. Migration Path

### Phase 0: Stabilize the Current Code

Goal:

- stop adding more business logic directly into CLI commands
- normalize current helper behavior before extracting it

Tasks:

- remove dead or duplicate analytics command code
- normalize `_get_mcp_*` signatures
- add or improve tests for existing analytics paths

Deliverable:

- current local mode remains stable

### Phase 1: Extract Shared Service

Goal:

- move analytics behavior into `socialhub_core`

Tasks:

- add `RequestContext`
- add `AnalyticsService`
- add `AnalyticsRepository`
- move query orchestration out of CLI

Deliverable:

- CLI still works
- MCP still works
- both use shared service

### Phase 2: Add API Service

Goal:

- allow CLI to call a remote API

Tasks:

- create `api_server`
- expose `/api/analytics/*`
- add CLI remote mode

Deliverable:

- local API can run
- CLI can switch between local and remote-api

### Phase 3: Remote MCP

Goal:

- allow Claude Desktop to connect to remote MCP

Tasks:

- run MCP with remote transport
- add reverse proxy and HTTPS
- add token-based auth

Deliverable:

- internal users can use remote Claude MCP

### Phase 4: Tenant, Audit, and Cache

Goal:

- make the platform production-ready

Tasks:

- token to tenant mapping
- Redis caching
- audit logging
- metrics and monitoring

Deliverable:

- platform-grade operational support

### Phase 5: Async Jobs and Large Reports

Goal:

- support long-running or large-output analytics tasks

Tasks:

- add a job system
- add report workers
- persist generated results

Deliverable:

- support for asynchronous complex reporting

## 11. Rollback Strategy

### 11.1 Runtime Modes

Keep three runtime modes available during migration:

- `local`
- `remote-api`
- `remote-mcp`

If remote services fail:

- CLI can switch back to `local`
- Claude Desktop can temporarily switch back to local bridge mode

### 11.2 Release Strategy

Recommended rollout:

- start with a small set of users on remote services
- keep local mode for the core team during rollout
- migrate one analytics domain at a time

## 12. Test Strategy

### 12.1 Unit Tests

Required coverage:

- service-layer validation
- permission checks
- cache key behavior
- tenant resolution

### 12.2 Integration Tests

Required coverage:

- API -> service -> repository
- MCP -> service -> repository
- CLI remote -> API

### 12.3 End-to-End Tests

Required coverage:

- Claude Desktop remote MCP overview query
- CLI orders and product queries
- timeout and cache behavior on larger windows

### 12.4 Key Acceptance Scenarios

Required scenarios:

1. `analytics_overview 30d`
2. `analytics_overview 365d`
3. `analytics_orders group_by=channel 365d`
4. `analytics_orders group_by=product 365d`
5. `analytics_funnel 365d`
6. tenant isolation across different auth contexts

## 13. Delivery Epics

### Epic 1: Shared Domain Extraction

- create `socialhub_core`
- add `RequestContext`
- add `AnalyticsService`
- add `AnalyticsRepository`

### Epic 2: API Layer

- create `api_server`
- add FastAPI
- add auth middleware
- add CLI remote client

### Epic 3: MCP Service Refactor

- refactor [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py)
- support remote deployment
- unify context handling

### Epic 4: Infrastructure

- Redis
- audit log
- metrics
- Docker and Nginx

### Epic 5: Platform Capabilities

- tenant isolation
- permission model
- async jobs
- reporting output pipeline

## 14. Docker And Deployment

### 14.1 Recommended Components

Recommended deployable components:

- API service
- MCP service
- Redis
- reverse proxy

### 14.2 Deployment Principle

Do not deploy duplicated analytics logic in multiple services.
Deploy thin delivery layers over the same shared service domain.

## 15. Minimum Viable Remote Version

If the goal is to get to a useful remote version quickly, the minimum scope should be:

1. extract analytics query logic into service and repository
2. add API service
3. make CLI prefer remote API
4. deploy MCP service remotely over SSE
5. add bearer token auth
6. add Redis caching
7. add HTTPS through Nginx

That version is enough to support:

- remote Claude Desktop usage
- continued CLI usage
- centralized analytics access
- centralized logging and version control

## 16. First-Batch Code Change Checklist

Recommended implementation order:

1. create `socialhub_core/context/request_context.py`
2. create `socialhub_core/domain/analytics/models.py`
3. create `socialhub_core/domain/analytics/service.py`
4. create `socialhub_core/adapters/warehouse/analytics_repository.py`
5. move `_get_mcp_overview`, `_get_mcp_orders`, and `_get_mcp_products` from [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) and related analytics modules into repository and service
6. update [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py) so handlers call the service layer
7. create `api_server/app.py`
8. create `api_server/routers/analytics.py`
9. create `cli/remote/client.py`
10. make CLI prefer remote mode when configured
11. create `deploy/nginx.conf`
12. create `docker-compose.yml`

## 17. Conclusion

For the Claude Desktop scenario, the correct direction is not simply "move the local script to a server."

The correct direction is:

- centralize business logic in a shared backend service layer
- make both MCP and CLI thin delivery channels
- make user and tenant context request-scoped
- centralize auth, cache, audit, and monitoring on the server side

The current repository already has the foundation for this migration. It does not need a full rewrite.

The practical path is:

1. extract shared service and repository logic
2. add API service
3. migrate MCP to remote deployment
4. add tenant and platform capabilities after the core service path is stable

## 18. Development Spec Addendum

This section turns the migration proposal into a development-ready spec. If this section conflicts with earlier high-level guidance, this section wins.

### 18.1 First-Batch Scope

The first migration batch is intentionally limited to four stable analytics capabilities:

- `overview`
- `orders`
- `customers`
- `report`

Out of scope for this batch:

- full migration of every `_get_mcp_*` function
- Skills, Heartbeat, AI, and fine-grained authorization redesign
- web frontend integration
- asynchronous large-report jobs

Migration map:

| Current location | Current capability | Target location | Notes |
|---|---|---|---|
| [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) | `analytics_overview()` | `socialhub_core/domain/analytics/service.py` | CLI keeps Typer args and rendering; orchestration moves to service |
| [cli/analytics/overview.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/overview.py) | `_get_mcp_overview()` | `socialhub_core/adapters/warehouse/analytics_repository.py` | pure data access moves to repository |
| [cli/analytics/orders.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/orders.py) | `_get_mcp_orders()` | `socialhub_core/adapters/warehouse/analytics_repository.py` | orders query moves down |
| [cli/analytics/customers.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/customers.py) | `_get_mcp_customers()` | `socialhub_core/adapters/warehouse/analytics_repository.py` | customers query moves down |
| [cli/analytics/report.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/report.py) | `_get_mcp_report()` | `socialhub_core/domain/analytics/service.py` + repository | report data fetch and business assembly are split |
| [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py) | overview/orders MCP handlers | `mcp_server/handlers/analytics.py` | handler becomes protocol-only and calls service |

Definition of done:

- CLI keeps working for these 4 capabilities
- MCP for these 4 capabilities goes through shared service
- numeric results stay consistent with pre-migration behavior
- old and new paths can coexist during rollout

### 18.2 Service Interface Contract

Only four public service methods exist in the first batch:

```python
from socialhub_core.context.request_context import RequestContext
from socialhub_core.domain.analytics.models import (
    OverviewQuery,
    OverviewResult,
    OrdersQuery,
    OrdersResult,
    CustomersQuery,
    CustomersResult,
    ReportQuery,
    ReportResult,
)


class AnalyticsService:
    def get_overview(self, ctx: RequestContext, query: OverviewQuery) -> OverviewResult: ...
    def get_orders(self, ctx: RequestContext, query: OrdersQuery) -> OrdersResult: ...
    def get_customers(self, ctx: RequestContext, query: CustomersQuery) -> CustomersResult: ...
    def get_report(self, ctx: RequestContext, query: ReportQuery) -> ReportResult: ...
```

Minimum Query / Result models:

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SourceMeta:
    source_layer: str
    source_table: str
    data_as_of: str | None = None
    query_window: str | None = None
    caveats: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OverviewQuery:
    period: str = "7d"
    from_date: str | None = None
    to_date: str | None = None
    compare: bool = False


@dataclass(slots=True)
class OverviewResult:
    summary: dict[str, Any]
    comparison: dict[str, Any] | None
    source_meta: SourceMeta


@dataclass(slots=True)
class OrdersQuery:
    period: str = "30d"
    from_date: str | None = None
    to_date: str | None = None
    metric: str = "sales"
    by: str | None = None


@dataclass(slots=True)
class OrdersResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    source_meta: SourceMeta


@dataclass(slots=True)
class CustomersQuery:
    period: str = "30d"
    from_date: str | None = None
    to_date: str | None = None
    customer_type: str = "all"


@dataclass(slots=True)
class CustomersResult:
    rows: list[dict[str, Any]]
    summary: dict[str, Any]
    source_meta: SourceMeta


@dataclass(slots=True)
class ReportQuery:
    topic: str
    period: str = "30d"
    from_date: str | None = None
    to_date: str | None = None
    formats: list[str] = field(default_factory=lambda: ["md"])


@dataclass(slots=True)
class ReportResult:
    markdown: str
    summary: dict[str, Any]
    source_meta: SourceMeta
```

Exception contract:

- invalid params: `ValueError`
- permission denied: `PermissionError`
- upstream data access failure: `UpstreamDataError`
- empty but valid business result: return empty rows or summary; do not throw

### 18.3 Repository Interface Contract

Repository is data-access only. It must not build business narratives, Rich output, or protocol payloads.

```python
class AnalyticsRepository:
    def fetch_overview(self, ctx: RequestContext, query: OverviewQuery) -> dict: ...
    def fetch_orders(self, ctx: RequestContext, query: OrdersQuery) -> dict: ...
    def fetch_customers(self, ctx: RequestContext, query: CustomersQuery) -> dict: ...
    def fetch_report_dataset(self, ctx: RequestContext, query: ReportQuery) -> dict: ...
```

Repository rules:

- always accept `RequestContext`
- return raw Python data only
- may assemble SQL or MCP requests
- must not do tenant permission decisions
- must not produce business recommendations

### 18.4 Layer Boundaries And Prohibited Patterns

CLI responsibilities:

- accept Typer arguments
- build `Query` models
- call service
- render Rich output
- export local files

MCP handler responsibilities:

- accept MCP params
- build `RequestContext` and `Query`
- call service
- return MCP protocol responses

API router responsibilities:

- accept HTTP requests
- parse auth information
- build `RequestContext` and `Query`
- call service
- return JSON

Service responsibilities:

- validate parameters
- apply business definitions
- orchestrate multi-query logic
- check permissions and tenant constraints
- assemble result models

Repository responsibilities:

- execute MCP / SQL / warehouse queries
- return raw datasets

Prohibited patterns:

- CLI command layer must not call the new repository directly
- MCP handlers must not import old `_get_mcp_*` helpers
- API routers must not write SQL or talk directly to `MCPClient`
- service must not emit Rich components
- repository must not return presentation strings for terminal output

### 18.5 RequestContext Standard

`RequestContext` is mandatory for all service and repository entry points. Required first-batch fields:

| Field | Required | Notes |
|---|---|---|
| `request_id` | Yes | per-request unique ID |
| `trace_id` | Yes | cross-system trace ID |
| `user_id` | Yes | caller identity |
| `tenant_id` | Yes | active tenant |
| `roles` | Yes | role list |
| `source` | Yes | `cli` / `api` / `mcp` |
| `metadata` | No | extensible context |

Source rules:

- CLI local mode: build from local config and runtime
- CLI remote mode: server resolves user and tenant from token; CLI passes trace info only
- API: auth middleware injects context
- MCP: remote gateway injects context

### 18.6 CLI / API / MCP Call Chains

CLI local mode:

```text
Typer command
  -> Query model
  -> AnalyticsService
  -> AnalyticsRepository
  -> MCP backend / database
  -> result
  -> Rich render
```

CLI remote mode:

```text
Typer command
  -> remote client
  -> API router
  -> AnalyticsService
  -> AnalyticsRepository
  -> result JSON
  -> Rich render
```

Remote MCP mode:

```text
Claude Desktop
  -> Remote MCP Gateway
  -> MCP handler
  -> AnalyticsService
  -> AnalyticsRepository
  -> result
  -> MCP response
```

Disallowed first-batch call chains:

- `mcp_server -> cli.commands.analytics -> cli.analytics.*`
- `api_router -> cli.commands.analytics`
- `cli.command -> repository`

### 18.7 Configuration And Runtime Modes

Supported first-batch runtime modes:

- `local`
- `remote-api`
- `remote-mcp`

Recommended new config:

```toml
[analytics]
mode = "local"
api_base_url = ""
mcp_base_url = ""
timeout_seconds = 60
default_database = "default"

[auth]
mode = "local"
token = ""
```

Runtime rules:

- local development defaults to `local`
- API integration defaults to `remote-api`
- Claude Desktop integration defaults to `remote-mcp`
- production CLI should prefer `remote-api`

Fallback requirements:

- CLI must be able to switch back to `local`
- remote failure must produce a clear error and fallback suggestion

### 18.7.1 Local Runtime Modes

To make local usage simpler for end users without making development chaotic, local operation must be split into explicit modes.

#### Mode A: `remote-user`

Target user:

- end users
- analysts
- operators using the CLI as a client

Local requirements:

- installed CLI
- access token
- remote API base URL, and optionally remote MCP URL

Local components started:

- none

Characteristics:

- simplest local setup
- no local warehouse credentials
- no local API service
- no local MCP bridge
- recommended default for production users

#### Mode B: `remote-dev`

Target user:

- most developers
- contributors working on CLI UX, output rendering, AI orchestration, and command composition

Local requirements:

- installed CLI
- developer token
- dev or staging API base URL

Local components started:

- none

Characteristics:

- local code changes can be tested against shared dev services
- avoids forcing every developer to run the full backend stack
- recommended default for day-to-day development unless backend internals are being changed

#### Mode C: `local-lite`

Target user:

- backend developers working on API, service, and repository logic

Local requirements:

- local API service
- optional local MCP service
- remote upstream analytics backend, or a stable shared test backend

Local components started:

- `api_service`
- optional `mcp_service`

Characteristics:

- service-layer changes can be tested locally
- still avoids requiring a full local data platform
- preferred mode for most backend feature work

#### Mode D: `local-full`

Target user:

- platform engineers
- developers debugging transport, cache, auth, or end-to-end service wiring

Local requirements:

- local API service
- local MCP service
- local Redis
- local reverse proxy if needed
- mock or real upstream analytics backend configuration

Local components started:

- `api_service`
- `mcp_service`
- `redis`
- optional `nginx`

Characteristics:

- highest fidelity local environment
- highest setup cost
- should be used only when lower-cost modes are insufficient

#### Default recommendations

- production users: `remote-user`
- most developers: `remote-dev`
- backend/service development: `local-lite`
- platform/infrastructure debugging: `local-full`

#### Design rule

The architecture must optimize for:

- the simplest possible local experience for end users
- a layered local development experience for engineers

The system must not assume that every local developer will run the full service stack.

### 18.8 Test Plan Addendum

The first migration batch must add all of the following tests.

Unit tests:

- validation for `OverviewQuery`, `OrdersQuery`, `CustomersQuery`, and `ReportQuery`
- `AnalyticsService` handling for empty data, invalid params, and permission denial
- `AnalyticsRepository` request assembly and result mapping

Consistency regression tests:

- new overview path matches old overview path
- new orders path matches old orders path
- new customers path matches old customers path
- report key summary fields match

Integration tests:

- API -> service -> repository
- MCP handler -> service -> repository
- CLI remote client -> API

End-to-end tests:

- `sh analytics overview --period=30d`
- `sh analytics orders --period=30d --by=channel`
- `sh analytics customers --period=30d`
- `sh analytics report --topic="Monthly analysis"`

Acceptance thresholds:

- first-batch CLI capabilities remain usable
- core metrics are identical, or only differ by acceptable floating-point tolerance
- MCP handler no longer depends on CLI query implementation
- API, MCP, and CLI all reach the shared service layer

### 18.9 Delivery Phases

Phase A: domain layer

- create `socialhub_core/context/request_context.py`
- create `socialhub_core/domain/analytics/models.py`
- create `socialhub_core/domain/analytics/service.py`
- create `socialhub_core/adapters/warehouse/analytics_repository.py`

Phase B: migrate first-batch capabilities

- migrate overview
- migrate orders
- migrate customers
- migrate report

Phase C: delivery-layer integration

- create `api_server/routers/analytics.py`
- split `mcp_server/handlers/analytics.py`
- make CLI local mode call service
- make CLI remote mode call API

Phase D: regression and rollout

- add consistency regression tests
- add remote-path integration tests
- gradually switch selected users to `remote-api`

### 18.10 First-Batch Acceptance Criteria

The batch is complete only if all conditions below are true:

1. [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) no longer carries the core query orchestration for the first 4 migrated capabilities.
2. [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py), or its new handlers, no longer depend directly on old `_get_mcp_*` query helpers.
3. Existing CLI behavior does not regress after introducing service and repository.
4. Configuration supports both `local` and `remote-api`.
5. Documentation, tests, and runtime instructions are updated together.

## 19. API Contract Appendix

This appendix defines the first-batch HTTP contracts for the remote API.

### 19.1 Common Rules

- All analytics APIs use `POST`
- Authentication uses bearer token unless `auth.mode=local`
- Successful responses use the envelope:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

- Error responses use the envelope:

```json
{
  "error": {
    "code": "invalid_query",
    "message": "Invalid period value",
    "details": {}
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### 19.2 `POST /api/analytics/overview`

Request:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "compare": true
}
```

Success response:

```json
{
  "data": {
    "summary": {
      "gmv": 123456.78,
      "orders": 3210,
      "buyers": 1280
    },
    "comparison": {
      "gmv_change_pct": 0.12
    },
    "source_meta": {
      "source_layer": "dws",
      "source_table": "dws_order_base_metrics_d",
      "data_as_of": "2026-03-28",
      "query_window": "2026-02-28..2026-03-28",
      "caveats": []
    }
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### 19.3 `POST /api/analytics/orders`

Request:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "metric": "sales",
  "by": "channel"
}
```

Success response:

```json
{
  "data": {
    "rows": [
      {
        "channel": "wechat",
        "sales": 45678.9,
        "orders": 980
      }
    ],
    "summary": {
      "sales": 123456.78,
      "orders": 3210
    },
    "source_meta": {
      "source_layer": "dws",
      "source_table": "dws_order_base_metrics_d",
      "data_as_of": "2026-03-28",
      "query_window": "2026-02-28..2026-03-28",
      "caveats": []
    }
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### 19.4 `POST /api/analytics/customers`

Request:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "customer_type": "all"
}
```

Success response:

```json
{
  "data": {
    "rows": [
      {
        "segment": "members",
        "count": 1024
      }
    ],
    "summary": {
      "total_customers": 1024,
      "buyers": 680
    },
    "source_meta": {
      "source_layer": "dws",
      "source_table": "dws_customer_base_metrics",
      "data_as_of": "2026-03-28",
      "query_window": "2026-02-28..2026-03-28",
      "caveats": []
    }
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### 19.5 `POST /api/analytics/report`

Request:

```json
{
  "topic": "Monthly analysis",
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "formats": ["md"]
}
```

Success response:

```json
{
  "data": {
    "markdown": "# Monthly analysis\\n...",
    "summary": {
      "topic": "Monthly analysis"
    },
    "source_meta": {
      "source_layer": "dws",
      "source_table": "dws_order_base_metrics_d",
      "data_as_of": "2026-03-28",
      "query_window": "2026-02-28..2026-03-28",
      "caveats": []
    }
  },
  "meta": {
    "request_id": "req_123",
    "trace_id": "trace_123"
  }
}
```

### 19.6 Error Codes

First-batch standard error codes:

- `invalid_query`
- `permission_denied`
- `tenant_not_resolved`
- `upstream_unavailable`
- `timeout`
- `internal_error`

## 20. MCP Tool Mapping Appendix

This appendix defines how first-batch MCP tools map to the shared service layer.

| MCP tool | Service method | Query model | Notes |
|---|---|---|---|
| `analytics_overview` | `AnalyticsService.get_overview` | `OverviewQuery` | MCP params map directly to query fields |
| `analytics_orders` | `AnalyticsService.get_orders` | `OrdersQuery` | `group_by` is normalized to `by` |
| `analytics_customers` | `AnalyticsService.get_customers` | `CustomersQuery` | `type` may map to `customer_type` |
| `analytics_report` | `AnalyticsService.get_report` | `ReportQuery` | Tool input should not contain file export paths |

Parameter normalization rules:

- `group_by` -> `by`
- `type` -> `customer_type`
- missing optional params use query model defaults
- MCP handlers must validate and normalize before calling service

MCP handler output rules:

- return structured machine-readable result
- do not embed Rich formatting
- do not call CLI render helpers

## 21. Function-Level Migration Table

This table defines the first-batch function migration at implementation level.

| Current file | Current function | Action | New home | Notes |
|---|---|---|---|---|
| [cli/analytics/overview.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/overview.py) | `_get_mcp_overview` | Move | `socialhub_core/adapters/warehouse/analytics_repository.py` | Repository data retrieval |
| [cli/analytics/overview.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/overview.py) | `_get_mcp_overview_compare_both` | Move | `socialhub_core/domain/analytics/service.py` + repository | Split orchestration from raw fetch |
| [cli/analytics/orders.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/orders.py) | `_get_mcp_orders` | Move | `socialhub_core/adapters/warehouse/analytics_repository.py` | Repository fetch |
| [cli/analytics/orders.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/orders.py) | `_orders_metrics_query` | Move | `socialhub_core/adapters/warehouse/analytics_repository.py` | Internal repository helper |
| [cli/analytics/customers.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/customers.py) | `_get_mcp_customers` | Move | `socialhub_core/adapters/warehouse/analytics_repository.py` | Repository fetch |
| [cli/analytics/report.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/report.py) | `_get_mcp_report` | Move | `socialhub_core/adapters/warehouse/analytics_repository.py` | Raw report dataset fetch |
| [cli/analytics/report.py](/C:/Users/86185/Socialhub-CLI/cli/analytics/report.py) | `_build_report_markdown` | Keep | existing file or report service helper | Presentation/report assembly decision allowed |
| [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) | `analytics_overview` | Refactor | stays in CLI | Command shell only |
| [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) | `analytics_orders` | Refactor | stays in CLI | Command shell only |
| [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) | `analytics_customers` | Refactor | stays in CLI | Command shell only |
| [cli/commands/analytics.py](/C:/Users/86185/Socialhub-CLI/cli/commands/analytics.py) | `analytics_report` | Refactor | stays in CLI | Command shell only |
| [mcp_server/server.py](/C:/Users/86185/Socialhub-CLI/mcp_server/server.py) | overview/orders handlers | Refactor | `mcp_server/handlers/analytics.py` | Protocol-only handlers |

Deprecation rule:

- old `_get_mcp_*` helpers may remain temporarily as thin adapters during migration
- after parity is verified, direct callers must be removed

## 22. Acceptance Matrix

This matrix defines concrete first-batch acceptance checks.

| Capability | Input | Expected result | Verification method |
|---|---|---|---|
| Overview | `sh analytics overview --period=30d` | Same summary metrics as pre-migration | CLI regression test + fixture compare |
| Overview compare | `sh analytics overview --period=30d --compare` | Same compare output semantics | CLI regression test |
| Orders by channel | `sh analytics orders --period=30d --by=channel` | Same rows and summary | CLI regression test + API compare |
| Orders default | `sh analytics orders --period=30d` | Same totals and no missing fields | CLI regression test |
| Customers | `sh analytics customers --period=30d` | Same summary metrics | CLI regression test + API compare |
| Report | `sh analytics report --topic="Monthly analysis"` | Same core summary fields and non-empty markdown | CLI regression test |
| API overview | `POST /api/analytics/overview` | 200 with valid envelope | API integration test |
| API orders | `POST /api/analytics/orders` | 200 with valid envelope | API integration test |
| MCP overview | MCP `analytics_overview` | Structured result via shared service | MCP integration test |
| MCP orders | MCP `analytics_orders` | Structured result via shared service | MCP integration test |

Performance baseline for first batch:

- remote API overhead should not increase median request time by more than 20% for the same upstream query
- CLI startup may remain unchanged in this batch
- service extraction must not materially increase query latency for local mode

Sign-off rule:

The batch is not accepted unless:

- all matrix items pass
- API and MCP both call shared service
- at least one rollback path remains available

## 23. Example Fixtures Appendix

This appendix provides first-batch golden examples for development and regression testing.

### 23.1 Overview Fixture

Input:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "compare": false
}
```

Expected shape:

```json
{
  "summary": {
    "gmv": 123456.78,
    "orders": 3210,
    "buyers": 1280,
    "aov": 38.46
  },
  "comparison": null,
  "source_meta": {
    "source_layer": "dws",
    "source_table": "dws_order_base_metrics_d",
    "data_as_of": "2026-03-28",
    "query_window": "2026-02-28..2026-03-28",
    "caveats": []
  }
}
```

### 23.2 Orders Fixture

Input:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "metric": "sales",
  "by": "channel"
}
```

Expected shape:

```json
{
  "rows": [
    {
      "channel": "wechat",
      "sales": 45678.90,
      "orders": 980
    },
    {
      "channel": "store",
      "sales": 37777.00,
      "orders": 850
    }
  ],
  "summary": {
    "sales": 123456.78,
    "orders": 3210
  },
  "source_meta": {
    "source_layer": "dws",
    "source_table": "dws_order_base_metrics_d",
    "data_as_of": "2026-03-28",
    "query_window": "2026-02-28..2026-03-28",
    "caveats": []
  }
}
```

### 23.3 Customers Fixture

Input:

```json
{
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "customer_type": "all"
}
```

Expected shape:

```json
{
  "rows": [
    {
      "segment": "members",
      "count": 1024
    },
    {
      "segment": "visitors",
      "count": 2048
    }
  ],
  "summary": {
    "total_customers": 3072,
    "buyers": 680
  },
  "source_meta": {
    "source_layer": "dws",
    "source_table": "dws_customer_base_metrics",
    "data_as_of": "2026-03-28",
    "query_window": "2026-02-28..2026-03-28",
    "caveats": []
  }
}
```

### 23.4 Report Fixture

Input:

```json
{
  "topic": "Monthly analysis",
  "period": "30d",
  "from_date": null,
  "to_date": null,
  "formats": ["md"]
}
```

Expected shape:

```json
{
  "markdown": "# Monthly analysis\n\n## Summary\n...",
  "summary": {
    "topic": "Monthly analysis",
    "period": "30d"
  },
  "source_meta": {
    "source_layer": "dws",
    "source_table": "dws_order_base_metrics_d",
    "data_as_of": "2026-03-28",
    "query_window": "2026-02-28..2026-03-28",
    "caveats": []
  }
}
```

### 23.5 Fixture Rules

- Fixture values are illustrative, but field presence and types are normative
- Regression tests must compare structure and key numeric fields
- When source tables differ due to fallback behavior, tests must explicitly allow the approved fallback source

## 24. Field Constraints Appendix

This appendix defines first-batch field constraints for query models and public interfaces.

### 24.1 Common Field Rules

- `from_date` format: `YYYY-MM-DD`
- `to_date` format: `YYYY-MM-DD`
- if `from_date` and `to_date` are both present, they take precedence over `period`
- date ranges are inclusive unless explicitly documented otherwise
- null optional fields must be treated as unset, not as empty strings

### 24.2 `period` Constraints

Allowed first-batch values:

- `today`
- `7d`
- `30d`
- `90d`
- `365d`
- `ytd`
- `all`

Validation rules:

- any other value returns `invalid_query`
- if `from_date > to_date`, return `invalid_query`
- if only one of `from_date` or `to_date` is provided, validation must fail unless explicitly supported by that endpoint

### 24.3 `metric` Constraints For Orders

Allowed first-batch values:

- `sales`
- `volume`
- `atv`

Validation rules:

- unknown metric returns `invalid_query`
- service layer is responsible for normalizing aliases if aliases are later introduced

### 24.4 `by` Constraints For Orders

Allowed first-batch values:

- `channel`
- `province`
- `product`

Validation rules:

- unknown grouping value returns `invalid_query`
- output row schema may differ by grouping field, but summary schema must remain stable

### 24.5 `customer_type` Constraints

Allowed first-batch values:

- `all`
- `members`
- `visitors`

Validation rules:

- unknown value returns `invalid_query`

### 24.6 `formats` Constraints For Report

Allowed first-batch values:

- `md`

Deferred values for later phases:

- `html`
- `pdf`

Validation rules:

- unsupported format returns `invalid_query`
- first batch requires `markdown` in the response model even if additional formats are added later

### 24.7 Sorting, Pagination, And Empty Results

Sorting:

- first-batch APIs do not expose generic sort parameters
- each service method defines its own stable default ordering

Pagination:

- first batch does not introduce generic pagination
- if a response becomes too large, that capability must define explicit pagination in a later phase rather than adding silent truncation

Empty results:

- empty but valid query windows return `200`
- `rows` should be `[]`
- `summary` should remain present with zero-like values where appropriate
- `source_meta` must still be populated when the upstream source is known
