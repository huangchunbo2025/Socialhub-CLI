# Skills Store Technical Design

## Overview

The Skills Store is a FastAPI + PostgreSQL service that supports:

- Public skills catalog and skill detail pages
- Developer publishing and version upload
- Admin review, certification, and revocation
- Storefront user accounts and personal skill libraries
- Shared Web/CLI library sync through `/api/v1/users/*`

Current deployed backend:

- `https://skills-store-backend.onrender.com`

Current repository areas:

- Backend: [skills-store](C:\Users\86185\Socialhub-CLI\skills-store)
- React storefront: [frontend](C:\Users\86185\Socialhub-CLI\frontend)
- CLI consumer: [socialhub](C:\Users\86185\Socialhub-CLI\socialhub)

This document describes the implemented architecture and current contracts.

## Architecture

### Runtime components

1. FastAPI application
   - request routing
   - auth
   - catalog APIs
   - developer/admin workflows
   - storefront user APIs

2. PostgreSQL
   - source of truth for catalog, versions, reviews, certificates, storefront users, and web user libraries

3. React storefront
   - catalog
   - skill detail
   - storefront user login
   - user library page

4. CLI client
   - downloads and installs local skill packages
   - syncs authenticated user library to backend

### Deployment

- Backend: Render Web Service
- Database: Render Postgres
- Current public static storefront: GitHub Pages
- React storefront preview: GitHub Pages `react-preview/`

## Backend stack

- FastAPI
- SQLAlchemy 2.x async ORM
- Alembic
- PostgreSQL
- `asyncpg` for async runtime
- `psycopg` for Alembic
- JWT auth
- PBKDF2 password hashing
- Ed25519 certificate signing and verification support

## Data model

### Existing platform tables

#### `developers`

Purpose:

- skill authors
- store admins

Important fields:

- `email`
- `password_hash`
- `name`
- `role` = `developer | store_admin`
- `status`
- `saved_skills`

Notes:

- `saved_skills` is legacy bookmark/favorites behavior
- it is frozen and not used for the new shared library model

#### `skills`

Purpose:

- published catalog entries

Important fields:

- `developer_id`
- `name`
- `display_name`
- `summary`
- `description`
- `license_name`
- `license_url`
- `homepage_url`
- `category`
- `status`
- `featured`
- `tags`
- `runtime_requirements`
- `install_guidance`
- `security_review`
- `docs_sections`
- `download_count`

#### `skill_versions`

Purpose:

- uploaded and reviewed version records per skill

Important fields:

- `skill_id`
- `version`
- `status`
- `package_filename`
- `package_path`
- `package_size`
- `package_hash`
- `manifest_json`
- `scan_summary`
- `release_notes`
- `submitted_at`
- `published_at`

#### `skill_reviews`

Purpose:

- admin moderation workflow

#### `skill_certifications`

Purpose:

- issued signatures, serials, revocation state

### Storefront user tables

#### `users`

Purpose:

- storefront users who browse and manage a personal skill library

Important fields:

- `email`
- `password_hash`
- `name`
- `status`

Current status handling:

- only `active` is used in runtime logic

#### `user_skills`

Purpose:

- shared web library for storefront users

Important fields:

- `user_id`
- `skill_id`
- `skill_version_id`
- `is_enabled`
- `downloaded_at`
- `updated_at`

Constraints:

- unique `(user_id, skill_id)`

## Auth model

### Developer/admin auth

Endpoints:

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `PATCH /api/v1/auth/me`

JWT characteristics:

- `type = "developer"`
- `role = developer | store_admin`

Used by:

- developer portal APIs
- admin review APIs

### Storefront user auth

Endpoints:

- `POST /api/v1/users/register`
- `POST /api/v1/users/login`
- `GET /api/v1/users/me`

JWT characteristics:

- `type = "user"`
- no developer role semantics

Used by:

- `/api/v1/users/me/skills*`
- React storefront `/user-login` and `/user`
- CLI store login and library sync

## API surface

### Public catalog

Implemented:

- `GET /api/v1/categories`
- `GET /api/v1/skills`
- `GET /api/v1/skills/featured`
- `GET /api/v1/skills/{name}`
- `GET /api/v1/skills/{name}/versions`
- `GET /api/v1/skills/{name}/download`
- `GET /api/v1/skills/{name}/download-info`
- `POST /api/v1/skills/check-updates`
- `POST /api/v1/skills/verify`
- `GET /api/v1/crl`

### Developer APIs

Implemented:

- `GET /api/v1/developer/skills`
- `POST /api/v1/developer/skills`
- `GET /api/v1/developer/skills/{name}`
- `POST /api/v1/developer/skills/{name}/versions`

### Admin APIs

Implemented:

- `GET /api/v1/admin/reviews`
- `POST /api/v1/admin/reviews/{review_id}/start`
- `POST /api/v1/admin/reviews/{review_id}/approve`
- `POST /api/v1/admin/reviews/{review_id}/reject`
- `GET /api/v1/admin/stats`
- `POST /api/v1/admin/certifications/{certificate_serial}/revoke`

### Storefront user library APIs

Implemented:

- `POST /api/v1/users/register`
- `POST /api/v1/users/login`
- `GET /api/v1/users/me`
- `GET /api/v1/users/me/skills`
- `POST /api/v1/users/me/skills/{skill_name}`
- `DELETE /api/v1/users/me/skills/{skill_name}`
- `PATCH /api/v1/users/me/skills/{skill_name}/toggle`

Response shape for `GET /api/v1/users/me/skills`:

```json
{
  "data": {
    "items": [
      {
        "skill_name": "sales-daily-brief",
        "display_name": "Sales Daily Brief",
        "version": "1.0.0",
        "category": "analytics",
        "is_enabled": true,
        "downloaded_at": "2026-03-24T00:00:00Z",
        "description": "...",
        "package_hash": "..."
      }
    ],
    "total": 1
  }
}
```

## Web / CLI sync contract

### Product meaning of Web install

Web `Install` does not download a zip package.

It means:

- add the skill to the authenticated storefront user's library

Actual local package installation happens only in CLI:

```bash
socialhub skills install <skill-name>
```

### Source of truth split

Backend:

- `user_skills` is the source of truth for storefront library contents

CLI local machine:

- `~/.socialhub/skills/registry.json` is the source of truth for local execution

Practical outcome:

- Web controls library membership and web-visible enabled state
- CLI controls whether the package exists locally
- CLI sync is fire-and-forget after local operations

### CLI contract

The backend must stay compatible with CLI calls in:

- [store_client.py](C:\Users\86185\Socialhub-CLI\socialhub\cli\skills\store_client.py)

Current expected endpoints:

- `POST /api/v1/users/login`
- `GET /api/v1/users/me/skills`
- `POST /api/v1/users/me/skills/{name}`
- `DELETE /api/v1/users/me/skills/{name}`
- `PATCH /api/v1/users/me/skills/{name}/toggle`

## Security model

### Package scanning

Current scan service enforces:

- manifest presence and required fields
- archive validity
- package size limits
- risky file extension checks
- dangerous code pattern checks:
  - `eval(`
  - `exec(`
  - `pickle.loads(`
  - `os.system(`
  - `subprocess ... shell=True`

Dangerous packages are rejected with `422 INVALID_PACKAGE`.

### Certification and revocation

Implemented:

- Ed25519 signing on publish approval
- public verification endpoint
- CRL endpoint
- certificate revocation endpoint

### CORS

Backend allows:

- GitHub Pages storefront
- local dev ports including `4173` and `5173`

## Frontend state model

### Static site

The old `docs/` storefront still exists as the production-facing Pages site.

Status:

- retained for current public site
- no longer the preferred direction for new storefront behavior

### React storefront

Location:

- [frontend](C:\Users\86185\Socialhub-CLI\frontend)

Current routes:

- `/`
- `/login`
- `/user-login`
- `/skill/:name`
- `/user`

Current behavior:

- `/login` remains the developer/admin-oriented login flow
- `/user-login` is the storefront user login flow
- catalog cards can install/uninstall directly when user-authenticated
- detail page can install/uninstall directly when user-authenticated
- `/user` reads the backend user library and supports toggle/remove

## Migrations

Applied migration sequence in repo:

- `0001_initial_schema.py`
- `0002_skill_detail_content.py`
- `0003_developer_saved_skills.py`
- `0004_users_and_user_skills.py`

## Seed and demo accounts

Seed script:

- `python backend/seed.py`

Seeded developer/admin:

- `admin@skills-store.local` / `Admin123!`
- `developer@skills-store.local` / `Developer123!`

Storefront users are not pre-seeded by default in the same way; they can be created via:

- `POST /api/v1/users/register`

## Current verified state

Manually verified:

- admin bootstrap works
- CRL format works
- dangerous scan rejection works
- storefront user registration works
- storefront user login works
- empty user library works
- add/toggle/remove user library flow works
- React storefront catalog/detail/user flow works against deployed backend

## Known pending items

- add automated tests for `users` and `user_skills`
- verify end-to-end CLI sync against the deployed backend with real CLI commands
- decide whether to replace static `docs/` storefront with React storefront
- developer/admin React migration not started

## Primary file map

Backend core:

- [main.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\main.py)
- [config.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\config.py)
- [database.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\database.py)

Backend auth:

- [jwt.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\auth\jwt.py)
- [dependencies.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\auth\dependencies.py)
- [auth.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\services\auth.py)

Backend user library:

- [users.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\routers\users.py)
- [user_skills.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\routers\user_skills.py)
- [skills.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\services\skills.py)
- [user.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\models\user.py)
- [user_skill.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\models\user_skill.py)

React storefront:

- [App.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\App.jsx)
- [CatalogPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\CatalogPage.jsx)
- [SkillDetailPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\SkillDetailPage.jsx)
- [UserLoginPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\UserLoginPage.jsx)
- [UserPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\UserPage.jsx)
- [api.js](C:\Users\86185\Socialhub-CLI\frontend\src\lib\api.js)
- [session.js](C:\Users\86185\Socialhub-CLI\frontend\src\lib\session.js)
