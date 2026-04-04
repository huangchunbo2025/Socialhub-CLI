# SocialHub CLI — Architecture Reference Manual

**Architecture Reference Document**

---

**Document Type:** Architecture Reference  
**Version:** v2.0  
**Date:** April 2026  
**Audience:** Software Architects, Senior Engineers, Technical Review Committees  
**Confidentiality:** Internal

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Overall Architecture Decisions](#2-overall-architecture-decisions)
3. [Component Architecture Deep Dive](#3-component-architecture-deep-dive)
4. [Data Flow and Sequence Diagrams](#4-data-flow-and-sequence-diagrams)
5. [Security Architecture](#5-security-architecture)
6. [MCP Protocol Layer](#6-mcp-protocol-layer)
7. [Skills Plugin Architecture](#7-skills-plugin-architecture)
8. [Deployment Architecture](#8-deployment-architecture)
9. [Non-Functional Requirements](#9-non-functional-requirements)
10. [Architecture Decision Records (ADR)](#10-architecture-decision-records-adr)
11. [Interface Contracts](#11-interface-contracts)
12. [Known Technical Debt and Evolution Path](#12-known-technical-debt-and-evolution-path)
13. [Appendix A: Key File Index](#13-appendix-a-key-file-index)
14. [Appendix B: Hard Constraints Summary](#14-appendix-b-hard-constraints-summary)

---

## 1. System Context

### 1.1 Problem Statement

SocialHub CLI is a customer intelligence platform CLI designed for retail and ecommerce operating teams. The platform addresses three core problems:

- Business users cannot directly access the analytical database layer, which forces routine decisions to depend on the data team.
- Internal AI surfaces such as Claude or M365 Copilot cannot safely access enterprise business data out of the box.
- Third-party analytical extensions need a defensible isolation model before they can be allowed into enterprise workflows.

The CLI is therefore not just a command-line utility. It is the controlled execution and analysis entry point for a broader AI-enabled operating model.

### 1.2 System Boundary (C4 Context)

```text
                        ┌─────────────────────────────────────────────────────┐
                        │                  External Systems                   │
                        │                                                     │
  ┌──────────────┐      │  ┌─────────────────┐   ┌─────────────────────────┐ │
  │  CLI Users   │      │  │  Azure OpenAI   │   │  StarRocks (MCP Upstream)│ │
  │ Ops / Analysts│     │  │  (AI Provider)  │   │  (Analytics Database)   │ │
  └──────┬───────┘      │  └────────┬────────┘   └───────────┬─────────────┘ │
         │              │           │                         │               │
         │              └───────────┼─────────────────────────┼───────────────┘
         │                          │                         │
         ▼                          ▼                         ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                         SocialHub Platform                                 │
│                                                                            │
│  ┌─────────────────────────┐         ┌────────────────────────────────────┐│
│  │      CLI Application    │         │         MCP Server                 ││
│  │      (cli/ package)     │ ──MCP── │      (mcp_server/ package)         ││
│  └─────────────────────────┘         └────────────────────────────────────┘│
│                                                │                            │
│  ┌─────────────────────────┐                   │ HTTP Streamable            │
│  │      Skills Store       │                   ▼                            │
│  │ FastAPI + PostgreSQL    │      ┌────────────────────────┐                │
│  └─────────────────────────┘      │  M365 Copilot /       │                │
│                                   │  Claude Desktop /     │                │
│                                   │  GitHub Copilot       │                │
└───────────────────────────────────┴────────────────────────┴────────────────┘
                                           External AI Clients
```

The core boundary is intentional:
- the CLI is the primary local execution surface
- the MCP server is the governed external tool surface
- the Skills Store is the controlled extension surface

### 1.3 Key Stakeholders

| Stakeholder | Primary Concern |
|---|---|
| Operations and analytics teams | Fast access to business insight, natural-language workflows |
| Management | M365 Copilot integration without tool switching |
| Data engineering | MCP stability, tenant isolation, upstream contract clarity |
| Security teams | Supply-chain security, auditability, extension isolation |
| Third-party skill developers | Stable extension API and explicit permission boundaries |

---

## 2. Overall Architecture Decisions

### 2.1 Architectural Style

The system uses a **layered modular monolith** rather than a microservices-first design.

Rationale:
- The primary delivery unit is a locally installed CLI package, so service decomposition would not improve the user experience.
- The MCP server already provides a natural service boundary where remote access is required.
- Avoiding an unnecessary service mesh or distributed control plane keeps the platform operationally lighter and easier to reason about.

Exception:
- The Skills Store backend is deployed as a standalone web service because it serves public package discovery and distribution use cases.

### 2.2 Technology Selection Matrix

| Concern | Selected Technology | Alternatives Considered | Rationale |
|---|---|---|---|
| CLI framework | **Typer** | Click, argparse | Type-driven CLI definitions and strong help generation |
| Terminal rendering | **Rich** | colorama, curses | Better tables, progress UI, and cross-platform behavior |
| HTTP client | **httpx** | requests, aiohttp | Sync + async support and better protocol flexibility |
| Validation layer | **Pydantic v2** | dataclasses, attrs | Faster validation and cleaner schema handling |
| MCP protocol | **mcp >= 1.8** | custom SSE | Aligns with emerging ecosystem standards |
| ASGI server | **uvicorn + starlette** | FastAPI, Django | Lean runtime for a single-purpose protocol service |
| Cryptography | **cryptography (PyCA)** | nacl, raw OpenSSL bindings | Mature Ed25519 support and safer APIs |
| AI provider | **Azure OpenAI** | OpenAI, Anthropic | Better fit for enterprise compliance defaults |
| Plugin isolation | **monkey-patch sandbox** | Docker, WASM | No container dependency, faster startup for CLI usage |
| Skills Store DB | **PostgreSQL** | MySQL, SQLite | Strong transactional behavior and mature migration tooling |

### 2.3 Module Dependency Map

```text
cli/main.py (entrypoint)
    │
    ├── cli/auth/           Authentication layer
    │   ├── __init__.py     ← owns SUBPROCESS_AUTH_SKIP_ENV constant
    │   ├── gate.py         ← uses _find_first_command() for correct option handling
    │   ├── oauth_client.py
    │   └── token_store.py  ← 5-minute grace period for auth-server outages
    │
    ├── cli/ai/             AI processing layer
    │   ├── sanitizer.py
    │   ├── client.py
    │   ├── parser.py
    │   ├── validator.py
    │   ├── executor.py     ← imports SUBPROCESS_AUTH_SKIP_ENV from cli/auth/
    │   ├── insights.py
    │   ├── session.py
    │   └── trace.py
    │
    ├── cli/commands/       Typer command layer
    ├── cli/api/            HTTP and MCP client layer
    ├── cli/analytics/      Analytical function layer
    ├── cli/skills/         Plugin system layer
    ├── cli/output/         Terminal and file rendering layer
    └── cli/config.py       Configuration source of truth

mcp_server/
    ├── __main__.py
    ├── http_app.py
    ├── auth.py
    └── server.py
         └── depends on → cli/analytics/mcp_adapter.py
```

Key dependency rules:
- `cli/analytics/mcp_adapter.py` is the only stable boundary through which the MCP server can access analytical capability.
- `cli/auth/__init__.py` owns the `SUBPROCESS_AUTH_SKIP_ENV` constant. `cli/ai/executor.py` imports it from `cli/auth/` rather than defining it locally, keeping auth constants in one place.
- The AI layer is intentionally stateless or function-oriented where possible to keep testing simpler.
- `cli/config.py` is the single source of runtime configuration.

---

## 3. Component Architecture Deep Dive

### 3.1 CLI Entry Point (`cli/main.py`)

#### Three-layer routing engine

```python
def cli_entrypoint(query: str):
    # Layer 1: registered command routing (skips leading global options)
    cmd = _find_first_command(args)  # skips --output-format, -v, --session etc.
    if cmd in VALID_COMMANDS:
        return typer_app(query)

    # Layer 2: command replay shortcuts (exact match only)
    if query.strip().lower() in REPEAT_PHRASES:
        return replay_last_command()

    # Layer 3: Smart Mode
    _run_auth_gate()
    sanitized = sanitize_user_input(query)
    validate_input_length(sanitized, max=2000)
    response = call_ai_api(sanitized, session)
    steps = extract_plan_steps(response)
    if steps:
        for step in steps:
            valid, reason = validate_command(step.command)
            if not valid:
                log_security_event("invalid_ai_command", step.command, reason)
                continue
        execute_plan(steps)
    else:
        render(response)
```

The routing engine uses `_find_first_command()` to skip any leading global options (such as `--output-format`, `-v`, or `--session`) before identifying the sub-command token. This keeps common registered commands fast, preserves repeatability for known workflows, and only invokes AI when the query shape actually requires interpretation.

#### Key global variables

```python
_AUTH_EXEMPT_COMMANDS = {"auth", "config", "--help", "-h", "--version", "-v"}
REPEAT_PHRASES = {"repeat", "again", "redo", "!!", "重复", "再来一次"}
```

`REPEAT_PHRASES` matching is exact-match only (not substring), so inputs like `"repeat analytics"` will not trigger a replay. These sets ensure bootstrapping commands stay usable before authentication succeeds and that common analyst repetition patterns remain low-friction.

### 3.2 AI Processing Layer (`cli/ai/`)

#### Processing flow

```text
User Input
    │
    ▼
sanitizer.sanitize_user_input()
    │
    ▼
client.call_ai_api()
    │
    ▼
parser.extract_plan_steps()
    │
    ├── multi-step plan → validator.validate_command() → executor.execute_plan()
    └── single response → render()
    │
    ▼
insights.generate_insights()
    │
    ▼
trace.record()
```

The AI pipeline is explicitly split into:
- input cleansing
- remote reasoning
- plan extraction
- command validation
- controlled execution
- result summarization
- trace persistence

#### Session state model

Sessions use lazy persistence (`persist=False` by default) — no disk write occurs until `add_turn()` followed by `save()`. Single-turn queries create ephemeral sessions so that memory extraction (insights and summaries) still runs even for one-off queries. Both `main.py` and `commands/ai.py` share session creation logic through `SessionStore.load_or_create()`.

```text
       create (ephemeral, no disk write)
            │
            ▼
       ┌──────────┐      add_turn + save
       │ IN-MEMORY │ ──────────────────────► PERSISTED (disk)
       └──────────┘                              │ TTL=24h
                                                 ▼
                                            ┌─────────┐
                                            │ EXPIRED │
                                            └─────────┘
```

Session files are stored under `~/.socialhub/sessions/{session_id}.json` and protected with file locking to reduce multi-process contention.

#### Circuit breaker

```python
class CircuitBreaker:
    """
    CLOSED -> OPEN -> HALF_OPEN -> CLOSED
    Trigger: 3 consecutive failures for the same command prefix
    Recovery timeout: 60 seconds
    """
```

This prevents unstable downstream paths from repeatedly degrading the user experience.

### 3.3 Configuration Layer (`cli/config.py`)

#### Pydantic v2 model hierarchy

```python
class SocialhubConfig(BaseModel):
    config_version: int = 1          # schema migration marker
    ai: AIConfig                     # includes openai_base_url for OpenAI-compatible services
    mcp: MCPConfig
    network: NetworkConfig
    session: SessionConfig
    trace: TraceConfig
    skills: SkillsConfig
    oauth: OAuthConfig
```

The configuration hierarchy is designed to keep operational concerns separated without creating multiple competing configuration sources.

Additional runtime behaviors:
- **Schema migration**: `config_version` enables forward-compatible schema evolution. Loaders can detect and upgrade older config files on read.
- **OpenAI-compatible services**: `AIConfig.openai_base_url` allows pointing the OpenAI provider at any compatible endpoint.
- **mtime-based caching**: `load_config()` checks file mtime and avoids redundant disk reads within the same process.
- **File permissions**: config files are saved with `0o600` permissions to prevent other local users from reading secrets.
- **Unified env overrides**: all environment variable overrides are applied in `_apply_env_overrides()` as a single source of truth. Field-level `default_factory` no longer reads environment variables directly.

#### Configuration precedence

```text
1. Environment variable overrides (_apply_env_overrides — single entry point)
2. ~/.socialhub/config.json
3. Pydantic field defaults / bundled defaults.json
```

Environment variables have the highest precedence. All env reads go through `_apply_env_overrides()` so that precedence logic has a single source of truth. This model is predictable for architects and practical for deployment teams.

### 3.4 Authentication Layer (`cli/auth/`)

The `SUBPROCESS_AUTH_SKIP_ENV` constant is defined in `cli/auth/__init__.py` and imported by `cli/ai/executor.py`. This keeps all auth-related constants in one module.

The auth gate uses `_find_first_command()` (the same helper as the CLI routing engine) to correctly identify the target command even when global options precede it. This ensures that invocations such as `sh -v auth status` correctly resolve `auth` as auth-exempt.

The token store includes a 5-minute grace period for brief auth-server outages. If the auth server is unreachable but the cached token was valid within the last 5 minutes, the CLI allows the operation to proceed rather than failing immediately.

### 3.5 Memory System (`cli/memory/`)

The memory system spans four layers: L4 preferences, L3 analysis insights, L2 session summaries, and L4 business context.

Key behavioral details:
- **`is_empty` check**: now inspects `business_context` fields (industry, peak_seasons, kpi_baselines) and active campaigns in addition to preferences and insights/summaries. This prevents the system from treating a profile with business context as empty.
- **`make_insight_id` uniqueness**: insight IDs include numeric suffixes to prevent same-day same-topic overwrites. Multiple insights on the same topic within one day each receive a distinct ID.
- **Single-turn memory extraction**: single-turn queries now create ephemeral sessions (no immediate disk write) so that the memory extractor still runs. Insights and summaries are extracted even from one-off queries.
- **Lazy session persistence**: sessions are created with `persist=False`. No disk write occurs until `add_turn()` followed by `save()`.

### 3.6 Heartbeat Scheduler (`cli/commands/heartbeat.py`)

The heartbeat scheduler manages periodic health checks and scheduled tasks.

Key behaviors:
- **Auto-reset after execution**: periodic tasks (daily, weekly, hourly) automatically reset to `pending` status after execution completes, enabling the next scheduled run.
- **Per-task locking**: manual `sh heartbeat run` acquires a per-task lock to prevent concurrent execution of the same task.
- **Audit trail**: check records are appended on every check invocation (not just the first), building an audit trail of all executions over time.
- **Batch I/O**: all mutations are accumulated in memory during a run cycle and flushed with a single file write at the end, reducing disk I/O.

### 3.7 MCP Server (`mcp_server/`)

#### Middleware stack

```text
HTTP Request
    │
    ▼
CORSMiddleware
    │
    ▼
RequestLoggingMiddleware
    │
    ▼
APIKeyMiddleware
    │
    ▼
Router
  ├── GET /health
  └── POST /mcp
```

The stack prioritizes:
- interoperability with enterprise clients such as M365
- request tracing
- authentication before business handling

#### Tool invocation chain

```python
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Unified entry point for all tools.
    All exceptions must be handled here.
    """
```

Centralizing tool dispatch keeps governance, cache handling, and error semantics consistent.

#### Cache architecture

```text
Request
  │
  ├── TTL cache hit → return
  └── miss
       │
       ├── in-flight exists → wait
       └── owner path
            │
            ├── acquire semaphore(50)
            ├── execute handler
            ├── write cache
            └── release waiters
```

This design favors practical server-side efficiency over full distributed cache sophistication.

#### Multi-tenant isolation with ContextVar

```python
_tenant_id_var: ContextVar[str] = ContextVar("tenant_id", default="")
```

`ContextVar` was selected instead of `threading.local()` because the request model is asyncio-based. The isolation boundary must therefore follow the request task, not the process thread.

### 3.8 Analytics Adapter (`cli/analytics/mcp_adapter.py`)

This is one of the most important architectural boundaries in the system.

Its responsibilities are:
1. serve as the only stable analytical interface exposed to the MCP server
2. translate MCP tool arguments into analytics function parameters
3. return JSON payloads formatted for `TextContent` packaging

Critical rule:
- the MCP server must not import the CLI command layer directly

This keeps the remote protocol surface independent from Typer-specific command concerns.

---

## 4. Data Flow and Sequence Diagrams

### 4.1 Full natural-language analysis sequence

```text
User → CLI Main → Sanitizer → AI Client → Parser → Validator → Executor → StarRocks
```

The sequence model is intentionally staged:
- sanitize first
- reason second
- validate before execution
- summarize only after controlled execution returns

This is the minimum structure required for a governed Smart Mode.

### 4.2 MCP Server tool invocation sequence (HTTP mode)

```text
M365 Copilot → http_app.py → auth.py → server.py → mcp_adapter → StarRocks MCP
```

The sequence emphasizes that:
- authentication sets tenant context first
- cache and in-flight deduplication happen before analytical execution
- the adapter is the only place where protocol arguments become analytics requests

### 4.3 Skill installation sequence (10-stage pipeline)

```text
User → CLI Skills → Security Manager → Store Client → File System → Registry
```

Key pipeline phases:
1. fetch metadata
2. duplicate check
3. download
4. hash verification
5. signature verification
6. revocation-list check
7. manifest parse
8. permission display
9. extraction
10. registry write

This is not a convenience flow. It is the controlled supply-chain entry path for code extension.

---

## 5. Security Architecture

### 5.1 Layered security model

```text
Layer 5: Application Security
Layer 4: Business Logic Security
Layer 3: Execution Security
Layer 2: Plugin Security (Skills Zero Trust)
Layer 1: Transport Security
```

The system uses overlapping controls rather than a single hard perimeter.

The intent is straightforward:
- protect transport
- constrain execution
- govern extensions
- preserve traceability

### 5.2 Prompt-injection defense

```python
_CONTROL_MARKER_PATTERN = re.compile(
    r'\[(?:PLAN_START|PLAN_END|SCHEDULE_TASK|/SCHEDULE_TASK|STEP_[^\]]*)\]',
    re.IGNORECASE
)
```

The design goal is to strip control markers before model processing while still preserving the user’s analytical intent. That reduces the chance that parser-level control semantics are smuggled in through user text.

### 5.3 Skills cryptographic verification

```python
OFFICIAL_PUBLIC_KEY_B64 = "..."
KEY_FINGERPRINT = "sha256:..."
```

Skills are treated as supply-chain artifacts. Signature validation is therefore not an optional integrity feature; it is the first trust boundary before code is allowed onto the local system.

### 5.4 Three-layer sandbox implementation

```python
class SandboxManager:
    """
    Uses a global lock because monkey-patching affects process-global builtins.
    """
```

The sandbox controls:
- filesystem access
- network access
- process execution

The architectural trade-off is explicit:
- serial plugin execution is accepted in exchange for a lighter runtime model
- the design is optimized for enterprise CLI use, not for untrusted multi-tenant plugin concurrency

### 5.5 Audit log architecture

```python
class SecurityAuditLogger:
    """
    Writes NDJSON audit records to ~/.socialhub/security/audit.log
    """
```

The audit layer exists to support:
- security review
- incident investigation
- policy validation
- post-failure reconstruction

### 5.6 API key logging policy

MCP auth log messages include only a truncated key prefix (`key[:4]+"***"`) to reduce exposure risk. The previous format (`key[:8]`) was shortened because eight characters could be sufficient to brute-force short keys or narrow the search space in a log leak.

---

## 6. MCP Protocol Layer

### 6.1 Protocol version and transport model

| Item | Specification |
|---|---|
| MCP version | 1.8+ (HTTP Streamable Transport) |
| Legacy support | SSE + POST dual endpoints |
| Content types | `application/json` / `text/event-stream` |
| Authentication | `X-API-Key` or `Authorization: Bearer <key>` |
| Health endpoint | `GET /health` |

### 6.2 Tool definition conventions

Each tool definition is structured to give the model enough semantic clarity to choose the right tool while staying within token budget.

Core design principles:
- descriptive names
- high-signal descriptions
- explicit parameter enums
- safe defaults

### 6.3 Tool response contract

All tool handlers must:
1. return `list[TextContent]`
2. handle all exceptions internally
3. avoid returning an empty list

This is especially important for M365 compatibility, where empty or malformed tool responses are more likely to degrade orchestration behavior.

### 6.4 M365 projection constraints

Only a subset of the full tool catalog is projected into M365, primarily because token budget matters.

Projection criteria:
1. prioritize executive and management use cases
2. keep descriptions strong enough to improve tool selection quality
3. treat each added tool as a packaging and governance event, not just a config update

---

## 7. Skills Plugin Architecture

### 7.1 Skill package specification

```text
<skill-name>.zip
├── skill.yaml
├── main.py
├── requirements.txt
└── ...
```

The package format is deliberately simple. The governance model is carried more by validation and policy than by a complicated artifact format.

### 7.2 Dynamic command registration

Dynamic registration allows installed Skills to appear as valid CLI command surfaces without hard-coding them into the main application.

This matters because the validator must be able to recognize Skill commands if AI-generated plans are going to remain safe and executable.

### 7.3 Permission storage format

Permission state is persisted locally and tied to:
- grant time
- grant source
- granted permissions
- skill version
- signing-key fingerprint

That gives the runtime enough context to support review and revocation.

### 7.4 Registry format

The registry tracks:
- package identity
- install path
- version
- install timestamp
- checksum
- signature metadata

This is the minimum operational metadata required for extension lifecycle control.

---

## 8. Deployment Architecture

### 8.1 Deployment units

| Component | Form Factor | Runtime | Platform |
|---|---|---|---|
| CLI | pip package | Python 3.10+ | user workstation |
| MCP Server | Docker or pip + uvicorn | Python 3.10+ | Render Cloud |
| Skills Store backend | Docker or pip + uvicorn | Python 3.10+ | Render Cloud |
| Skills Store frontend | static site | Vite build | GitHub Pages |

### 8.2 MCP Server production deployment

The current production model is intentionally conservative:
- single worker
- health endpoint
- secret-managed API keys
- explicit transport endpoints

The `workers=1` constraint is deliberate because the current cache and in-flight deduplication model is process-local.

### 8.3 Network topology

The current topology is:
- internet-facing TLS termination at the cloud edge
- a single MCP service instance
- outbound MCP communication to the customer-owned StarRocks MCP layer

This keeps the protocol tier light while allowing analytical data authority to remain on the customer side.

### 8.4 Skills Store architecture

The store architecture separates:
- static storefront delivery
- backend authentication and package service
- PostgreSQL persistence

This split keeps the user-facing discovery surface easy to operate while preserving a normal service boundary for package and identity operations.

---

## 9. Non-Functional Requirements

### 9.1 Performance targets

| Metric | Target | Current Status | Notes |
|---|---|---|---|
| Registered CLI command response | < 100ms | ✅ | No AI overhead |
| Smart Mode end-to-end | < 30s P95 | ✅ | AI call dominates latency |
| MCP cache-hit response | < 50ms | ✅ | in-memory lookup |
| MCP cache-miss response | < 10s P95 | ⚠️ | depends on StarRocks |
| Skill install time | < 30s | ✅ | network-bound |
| MCP concurrency | 50 analytical executions | ✅ | semaphore bounded |

#### Analytics timezone convention

All analytics date computations use `datetime.now(timezone.utc)` consistently. Previous code paths used naive local time, which could produce incorrect date boundaries depending on the operator's timezone. UTC is now the single time reference for all analytical functions.

### 9.2 Reliability design

| Failure Mode | Response Strategy |
|---|---|
| AI API timeout | retries with backoff |
| AI API outage | registered commands continue to work |
| StarRocks MCP timeout | in-flight timeout and breaker protection |
| MCP server restart | cache reset accepted |
| Skills sandbox failure | restore patched globals and release lock |
| Skills Store outage | installed Skills continue to run |

### 9.3 Scalability constraints

Current single-instance limitations:
- process-local cache
- process-local in-flight deduplication
- process-local sandbox lock

Horizontal scale prerequisites:
- external shared cache
- distributed in-flight control
- revised plugin concurrency model

### 9.4 Observability

Current signal sources:
- uvicorn access logs
- security audit logs
- AI trace logs
- CLI history

Known gaps:
- Prometheus metrics
- end-to-end distributed tracing
- structured JSON logging across the MCP service

---

## 10. Architecture Decision Records (ADR)

### ADR-001: MCP over a custom REST API

**Status:** Accepted  
**Date:** 2025 Q4

Decision:
- adopt MCP 1.8+ instead of inventing a proprietary remote tool protocol

Consequences:
- native alignment with Claude, GitHub Copilot, and M365 Copilot
- better tool-schema standardization
- dependency on upstream MCP library stability

### ADR-002: Monkey-patch sandbox instead of Docker-based isolation

**Status:** Accepted  
**Date:** 2025 Q4

Decision:
- use process-level monkey-patching for CLI plugin isolation rather than container runtime isolation

Rationale:
- lower user friction
- faster startup
- better fit for a workstation-installed CLI

Known limitation:
- this is a pragmatic isolation layer, not a perfect hostile-code isolation boundary

### ADR-003: ContextVar for tenant isolation

Decision:
- use `ContextVar` instead of thread-local storage for per-request tenant state

Reason:
- the runtime model is asyncio-oriented, so request isolation must track tasks

### ADR-004: `mcp_adapter.py` as the stable interface boundary

Decision:
- create a formal adapter boundary between the MCP server and analytical functions

Reason:
- protect the protocol layer from CLI-specific coupling

### ADR-005: Store URL hard-coded, no config override

Decision:
- keep the official store endpoint fixed in product defaults

Reason:
- reduce supply-chain ambiguity
- avoid redirecting users to untrusted package sources through simple config changes

### ADR-006: `workers=1` for the MCP service

Decision:
- keep the current deployment single-worker

Reason:
- current cache, in-flight, and isolation logic are process-local

---

## 11. Interface Contracts

### 11.1 CLI ↔ Skills Store API

The Skills Store contract must support:
- package discovery
- metadata retrieval
- artifact download
- signature and checksum delivery
- revocation checks

This is fundamentally a supply-chain API, not just a package index.

### 11.2 MCP Server ↔ StarRocks MCP

This contract is the analytical execution path and must remain stable enough to support:
- deterministic argument mapping
- bounded response size
- predictable latency behavior
- tenant-safe routing

### 11.3 M365 Copilot ↔ MCP Server

This contract is the executive-facing tool surface.

That means compatibility is not only a syntax issue. It is also a question of:
- schema size
- tool clarity
- response predictability
- failure semantics

### 11.4 Skills package contract for third-party developers

Third-party developers must be able to understand:
- package shape
- manifest rules
- permission model
- signing expectations
- runtime restrictions

Without a clear contract, the extension ecosystem becomes operationally expensive to govern.

---

## 12. Known Technical Debt and Evolution Path

### 12.1 Debt inventory

Current technical debt includes:
- process-local cache and deduplication
- limited observability depth
- single-worker MCP service constraint
- monkey-patch isolation trade-offs
- OAuth token validation in MCP server auth (`_extract_tenant_id_from_token`) is an explicit stub — API Key auth is the only supported mode. The stub is protected by a 503 rejection when `MCP_API_KEYS` is not configured, so it cannot be reached in production.

These are known and documented design choices, not hidden defects.

### 12.2 Near-term path (2026 Q3–Q4)

Expected near-term improvements:
- stronger metrics collection
- better structured logs
- clearer operational dashboards
- refinement of store and extension governance

### 12.3 Mid-term path (2027+)

Likely architectural evolution areas:
- shared cache infrastructure
- stronger distributed coordination
- improved plugin isolation model
- more production-grade observability and trace correlation

---

## 13. Appendix A: Key File Index

Use this appendix as the fast navigation map for architecture review.

It should point reviewers to:
- CLI entry
- AI layer
- MCP service entry
- adapter boundary
- sandbox manager
- configuration models
- security logging

This appendix is especially useful during code walkthroughs and technical committee review sessions.

---

## 14. Appendix B: Hard Constraints Summary

Key hard constraints in the current architecture:
- MCP server must access analytics through the adapter boundary
- plugin execution is serialized under the global sandbox lock
- current multi-worker deployment is intentionally unsupported
- store trust is anchored in signature validation and controlled endpoint assumptions

These constraints should be treated as review guardrails, not implementation suggestions.
