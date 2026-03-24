# CODEX.md

## Current Status

This file is the current handoff note for the `Socialhub-CLI` Skills Store work.
If any older docs conflict with the current implementation state, use this file as the current execution summary.

## Branch And Deployment

- Active source branch: `render-clean`
- Storefront Pages: `https://huangchunbo2025.github.io/Socialhub-CLI/`
- React storefront preview: `https://huangchunbo2025.github.io/Socialhub-CLI/react-preview/`
- Backend API: `https://skills-store-backend.onrender.com`
- Backend service on Render: `SHCLI`

## What Has Been Completed

### 1. Storefront Static Site

The current public storefront in `docs/` has already been iterated into a usable multi-page static site.

Relevant files:

- [index.html](C:\Users\86185\Socialhub-CLI\docs\index.html)
- [skill.html](C:\Users\86185\Socialhub-CLI\docs\skill.html)
- [login.html](C:\Users\86185\Socialhub-CLI\docs\login.html)
- [user.html](C:\Users\86185\Socialhub-CLI\docs\user.html)
- [app.js](C:\Users\86185\Socialhub-CLI\docs\app.js)
- [styles.css](C:\Users\86185\Socialhub-CLI\docs\styles.css)

Current static storefront capabilities:

- Public catalog browsing
- Skill detail page with trust, runtime, install, versions
- Store user sign-in page
- Store user workspace page
- CLI install guidance
- GitHub Pages publishing

### 2. Backend MVP

The FastAPI backend has already been implemented and deployed.

Relevant directory:

- [skills-store](C:\Users\86185\Socialhub-CLI\skills-store)

Implemented areas:

- Auth: register, login, me, profile update
- Public catalog APIs
- Skill detail APIs
- Developer upload flow
- Admin review flow
- Certification and CRL flow
- Seed script for demo data
- Render deployment files

### 3. Detail Page Data Model Upgrade

The backend and seed data were extended to support richer skill detail content.

Implemented fields include:

- `license_name`
- `license_url`
- `homepage_url`
- `runtime_requirements`
- `install_guidance`
- `security_review`
- `docs_sections`

These are already returned by:

- `GET /api/v1/skills/{name}`

### 4. New React Storefront App

A new formal frontend app has now been created and verified.

Directory:

- [frontend](C:\Users\86185\Socialhub-CLI\frontend)

Tech stack:

- React
- Vite
- React Router

Current React routes:

- `/` catalog
- `/login`
- `/user-login`
- `/skill/:name`
- `/user`

Implemented in React:

- Catalog page
- Skill detail page
- Storefront user login page
- Store user workspace page
- Shared layout
- Session helpers
- Toast feedback
- Catalog card install / uninstall flow
- Skill detail install / uninstall flow
- My Skills page backed by storefront user library APIs

Verification already done:

- `npm install`
- `npm run build`

## Latest Completed Functional Change

The newest end-to-end change completed before this handoff is the shared storefront user library flow between backend, React storefront, and CLI contract.

Backend additions:

- [user.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\models\user.py)
- [user_skill.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\models\user_skill.py)
- [users.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\routers\users.py)
- [user_skills.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\routers\user_skills.py)
- [user.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\schemas\user.py)
- [dependencies.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\auth\dependencies.py)
- [jwt.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\auth\jwt.py)
- [skills.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\services\skills.py)
- [auth.py](C:\Users\86185\Socialhub-CLI\skills-store\backend\app\services\auth.py)
- [0004_users_and_user_skills.py](C:\Users\86185\Socialhub-CLI\skills-store\alembic\versions\0004_users_and_user_skills.py)

React storefront additions:

- [frontend](C:\Users\86185\Socialhub-CLI\frontend)
- [UserLoginPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\UserLoginPage.jsx)
- [UserPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\UserPage.jsx)
- [SkillDetailPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\SkillDetailPage.jsx)
- [CatalogPage.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\pages\CatalogPage.jsx)
- [SkillCard.jsx](C:\Users\86185\Socialhub-CLI\frontend\src\components\SkillCard.jsx)
- [api.js](C:\Users\86185\Socialhub-CLI\frontend\src\lib\api.js)
- [session.js](C:\Users\86185\Socialhub-CLI\frontend\src\lib\session.js)

Git commit:

- `03400c0` `Add storefront users and shared user skills library`
- `b2143a1` `Fix React storefront install actions and refresh preview`

## What Is Still Pending

### 1. Decide Frontend Cutover Strategy

The React storefront exists, but it has not yet replaced the current static `docs/` site.

Decision still needed:

- keep `docs/` as current production temporarily
- or deploy `frontend/` and replace Pages storefront

### 2. Finish React Storefront Productization

Still to do in React app:

- refine empty states
- improve error handling copy
- improve CLI modal/CLI guidance experience
- add stronger loading states
- decide deployment target

### 3. Developer/Admin React Migration

Not started.

Current developer/admin experience still lives in static `docs/` pages.

## Security / Implementation Constraints

These constraints should continue to be respected.

### Storefront

- Installation is CLI-first, not direct-download-first
- Public store should not expose developer or admin operations
- Store user flow must remain separate from developer/admin entry points

### Auth

- All permission checks must stay on the backend
- Frontend must not be treated as an authority for role checks
- Storefront session behavior should move toward backend-backed persistence, not more local-only state

### Backend

- Continue using current MVP boundaries
- Do not introduce multi-service complexity
- Tenant/enterprise phase work is now explicitly in scope — see Section: Tenant Management Feature below

## Test Accounts

Current demo accounts:

- Store/developer account:
  - `developer@skills-store.local`
  - `Developer123!`

- Admin account:
  - `admin@skills-store.local`
  - `Admin123!`

## Immediate Next Recommended Actions

1. Keep validating the React storefront preview at `react-preview`
2. Decide whether to replace the current static storefront with `frontend/`
3. Add minimal automated tests for storefront users and `user_skills`
4. Verify CLI end-to-end sync against the new `/api/v1/users/*` endpoints
5. Start developer/admin React migration only after storefront cutover decision

---

## Implementation Update

The user library task is no longer just planned. The following are already implemented and manually verified:

- Separate storefront `users` table and `user_skills` table
- `POST /api/v1/users/register`
- `POST /api/v1/users/login`
- `GET /api/v1/users/me`
- `GET /api/v1/users/me/skills`
- `POST /api/v1/users/me/skills/{skill_name}`
- `DELETE /api/v1/users/me/skills/{skill_name}`
- `PATCH /api/v1/users/me/skills/{skill_name}/toggle`
- React `/user-login`
- React catalog card `Install / Uninstall`
- React skill detail `Install / Uninstall`
- React `/user` page reading `My Skills` from `/api/v1/users/me/skills`

Manual verification already completed:

- Storefront user registration works
- Storefront user login works
- Empty library query works
- Add to library works
- Toggle enabled/disabled works
- Remove from library works
- React catalog/detail/user flow works against the deployed backend

`developers.saved_skills` remains in place but is now treated as frozen legacy behavior. The new shared library flow is `users` + `user_skills`.

## Task: User Skills Library (Web + CLI Sync)

> **Status**: Backend, React storefront, and CLI contract are aligned. Remaining work is tests, CLI end-to-end verification, and storefront cutover decisions.

---

### Hard Constraints — Read Before Anything Else

These rules resolve every ambiguity. If any other part of this document conflicts with them, these rules win.

1. **Account tables are strictly separated by role. Each role has its own table.**

   | Table | Who | Auth endpoints |
   |-------|-----|----------------|
   | `developers` | Skill authors, store admins | `POST /api/v1/auth/login` (existing, unchanged) |
   | `users` | Storefront users who browse/install skills | `POST /api/v1/users/login` (new) |

   Do NOT store storefront users in `developers`. Do NOT add a `user` role to the `developers` table.

2. **`saved_skills` is frozen**: `developers.saved_skills` (JSONB) is a developers-table feature that predates this task. Leave it exactly as-is. It has no role in the new user library feature.

3. **`user_skills.user_id` references `users(id)`, not `developers(id)`**: The installed library belongs to `users`, not `developers`.

4. **Only update `frontend/` — do not touch `docs/`**: `docs/` is the current live GitHub Pages site. All frontend changes go in `frontend/src/` only. `docs/` is frozen.

5. **Web "Install" = add to library only. No file download in browser.** Clicking Install calls `POST /api/v1/users/me/skills/{name}`. It records the skill in the user's library. The actual `.zip` download and local install happens only via CLI (`socialhub skills install`). The web never downloads or executes skill packages.

6. **Source of truth split**:
   - `backend user_skills` = source of truth for library contents → drives Web UI
   - `~/.socialhub/skills/registry.json` = source of truth for CLI execution → what can actually run locally
   - If web shows `is_enabled = false`, CLI reflects that on next authenticated `skills list` call.

---

### What Is Already Done

**CLI side — Claude Code has already implemented** (do NOT modify `socialhub/`):

- `socialhub/cli/skills/store_client.py`: `login()`, `logout()`, `is_authenticated()`, `get_my_skills()`, `add_my_skill()`, `remove_my_skill()`, `toggle_my_skill()`
- `socialhub/cli/commands/skills.py`: `login`, `logout` commands; `list` command shows user library when authenticated
- `socialhub/cli/skills/manager.py`: `install()`, `uninstall()`, `enable()`, `disable()` all call backend sync as fire-and-forget after completing local operations

**What CLI expects from the backend:**

Auth token contract — backend must match exactly:
- Login endpoint: `POST /api/v1/users/login` (storefront user login — NOT `/api/v1/auth/login` which is for developers)
- Login response shape (exact field names required):
  ```json
  { "data": { "access_token": "...", "expires_in": 86400, "user": { "name": "..." } } }
  ```
- All `/api/v1/users/me/` endpoints require: `Authorization: Bearer <token>` header

---

### Codex Backend Task

**Step 1: Alembic migration** — file: `skills-store/alembic/versions/0004_users_and_user_skills.py`

Two new tables in one migration:

```sql
-- Table 1: storefront users (separate from developers)
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         VARCHAR(200) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    name          VARCHAR(200) NOT NULL,
    status        VARCHAR(50)  NOT NULL DEFAULT 'active',
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);

-- Table 2: installed skills library (belongs to users, not developers)
CREATE TABLE user_skills (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill_id         BIGINT NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
    skill_version_id BIGINT NOT NULL REFERENCES skill_versions(id) ON DELETE RESTRICT,
    is_enabled       BOOLEAN     NOT NULL DEFAULT TRUE,
    downloaded_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, skill_id)
);
CREATE INDEX idx_user_skills_user ON user_skills(user_id);
```

**Step 2: SQLAlchemy models**

- `skills-store/backend/app/models/user.py` — `User` model for the `users` table
- `skills-store/backend/app/models/user_skill.py` — `UserSkill` model for the `user_skills` table

Use the same `TimestampMixin` and `Base` patterns as existing models.

**Step 3: User auth router** — file: `skills-store/backend/app/routers/users.py`

Register at prefix `/api/v1` in `main.py`.

| Method | Path | Auth | Action |
|--------|------|------|--------|
| `POST` | `/api/v1/users/register` | None | Register new storefront user |
| `POST` | `/api/v1/users/login` | None | Login, returns JWT |
| `GET` | `/api/v1/users/me` | JWT (user) | Get current user profile |

**`POST /api/v1/users/register` — request:**
```json
{ "email": "alice@example.com", "password": "...", "name": "Alice" }
```
- Duplicate email → 409
- Password hashed with same PBKDF2 approach used for developers

**`POST /api/v1/users/login` — request:**
```json
{ "email": "alice@example.com", "password": "..." }
```

**`POST /api/v1/users/login` — response (exact shape, CLI depends on this):**
```json
{
  "data": {
    "access_token": "<JWT>",
    "expires_in": 86400,
    "user": { "id": 1, "name": "Alice", "email": "alice@example.com" }
  }
}
```

JWT payload must include `sub` (user id as string) and a field to distinguish user type, e.g. `"type": "user"`, so that `get_current_user` dependencies can differentiate between a developer token and a user token.

**Step 4: User skills router** — file: `skills-store/backend/app/routers/user_skills.py`

Register at prefix `/api/v1` in `main.py`. All endpoints require a `get_current_storefront_user` dependency (reads JWT, looks up `users` table — separate from `get_current_developer` which reads `developers` table).

| Method | Path | Auth | Action |
|--------|------|------|--------|
| `GET` | `/api/v1/users/me/skills` | JWT (user) | Return user's library |
| `POST` | `/api/v1/users/me/skills/{skill_name}` | JWT (user) | Add to library |
| `DELETE` | `/api/v1/users/me/skills/{skill_name}` | JWT (user) | Remove from library |
| `PATCH` | `/api/v1/users/me/skills/{skill_name}/toggle` | JWT (user) | Enable or disable |

**`GET /api/v1/users/me/skills` — exact response shape** (CLI parses this; field names are fixed):

```json
{
  "data": {
    "items": [
      {
        "skill_name": "report-generator",
        "display_name": "Report Generator",
        "version": "1.1.0",
        "category": "utility",
        "is_enabled": true,
        "downloaded_at": "2026-03-22T10:00:00Z",
        "description": "..."
      }
    ],
    "total": 3
  }
}
```

**`POST /api/v1/users/me/skills/{skill_name}` — request body:**
```json
{ "version": "1.1.0" }
```
- `version` optional — defaults to latest published version
- Skill not published → 404
- Already in library → 409
- Success response: same shape as one item from the list above

**`DELETE /api/v1/users/me/skills/{skill_name}`**
- Not in library → 404
- Success → 204 No Content

**`PATCH /api/v1/users/me/skills/{skill_name}/toggle` — request body:**
```json
{ "enabled": true }
```
- Not in library → 404
- Success response: same shape as one item from the list above, with updated `is_enabled`

**Step 5: Deploy to Render**

Push to `render-clean` branch and run Manual Sync. Verify all endpoints before starting frontend work.

---

### Codex Frontend Task

**Only modify files under `frontend/src/`.** Do not touch `docs/`.

The existing React app already has these files Codex built:
- `frontend/src/pages/SkillDetailPage.jsx`
- `frontend/src/pages/UserPage.jsx`
- `frontend/src/lib/session.js` — contains `saved_skills` localStorage logic (do not delete; leave frozen)
- `frontend/src/lib/api.js` — existing API wrapper, add new calls here
- `frontend/src/pages/LoginPage.jsx` — current login calls `/api/v1/auth/login` (developer login)

**Important: the existing Login page authenticates against `developers` table (`/api/v1/auth/login`). Storefront users log in via `/api/v1/users/login`. These are two separate flows. Do NOT change the existing developer login. Add a new storefront user login.**

**Frontend Change 0: Add storefront user login** — `frontend/src/pages/UserLoginPage.jsx` (new file)

- Route: `/user-login`
- Calls `POST /api/v1/users/login`
- On success: store token in session (same `setSession()` helper, or a parallel `setUserSession()`)
- On success: redirect to `/user`
- Link from the existing `/login` page: *"Looking to use skills? Sign in as a user →"*

**Frontend Change 1: `frontend/src/pages/SkillDetailPage.jsx`**

On page load, check if storefront user is logged in (has a valid user token). Call `GET /api/v1/users/me/skills` and check if this skill's `skill_name` is in the response.

Replace the current "Save" / bookmark button with:
- User not logged in → show **"Login to Install"** → clicking navigates to `/user-login`
- User logged in, skill NOT in library → show **"Install"** button
  - On click: `POST /api/v1/users/me/skills/{name}` (body: `{}`)
  - On success: button changes to "Uninstall" without page reload
  - Show note below button: *"Added to your library. Run `socialhub skills install {name}` in CLI to use it."*
- User logged in, skill IN library → show **"Uninstall"** button
  - On click: `DELETE /api/v1/users/me/skills/{name}`
  - On success: button changes to "Install" without page reload

**Frontend Change 2: `frontend/src/pages/UserPage.jsx`**

The current page has a "Saved Skills" section that reads from `saved_skills` (via `session.js`). Replace that section entirely with **"My Skills"**:

- On page load: call `GET /api/v1/users/me/skills`
- Display a list/table of installed skills: Name, Version, Category, Enable/Disable toggle, Remove button
- Enable/Disable toggle:
  - `PATCH /api/v1/users/me/skills/{name}/toggle` with `{"enabled": <new_state>}`
  - Update toggle UI immediately on success
- Remove button:
  - `DELETE /api/v1/users/me/skills/{name}` → remove the row on success
- Empty state: *"Your library is empty. Browse the store to install skills."* with link to `/`
- If user is not logged in → redirect to `/user-login`

Do NOT delete or modify any `saved_skills`-related functions in `session.js`. They are frozen in place.

---

### Acceptance Criteria

**Backend (verify before starting frontend):**
- [ ] `POST /api/v1/users/register` creates a new row in `users` table (not `developers`)
- [ ] `POST /api/v1/users/login` returns `data.access_token` and `data.expires_in: 86400`
- [ ] Token from `/users/login` is rejected by developer-only endpoints (403)
- [ ] `POST /users/me/skills/report-generator` → skill appears in `GET /users/me/skills`
- [ ] `POST /users/me/skills/report-generator` again → 409
- [ ] `DELETE /users/me/skills/report-generator` → 204, skill gone from list
- [ ] `PATCH /users/me/skills/report-generator/toggle {"enabled": false}` → `is_enabled: false`
- [ ] User A's library is independent from User B's library
- [ ] Developer JWT cannot access `/users/me/skills` (must return 403)

**Frontend:**
- [ ] `/user-login` route exists and calls `/api/v1/users/login`
- [ ] Skill detail page shows "Login to Install" when not logged in as user
- [ ] Clicking "Install" → calls `/users/me/skills/{name}`, button becomes "Uninstall"
- [ ] Clicking "Uninstall" → calls `DELETE /users/me/skills/{name}`, button becomes "Install"
- [ ] User page loads "My Skills" from `/users/me/skills`
- [ ] Enable/Disable toggle calls toggle API, state persists on page reload
- [ ] Remove button removes skill from list immediately

**End-to-end (CLI + Web):**
- [ ] `socialhub skills login` (with user credentials) → token saved, calls `/api/v1/users/login`
- [ ] Install via CLI → skill appears in web user page on next load
- [ ] Click Install on web → `socialhub skills list` (authenticated) shows the skill
- [ ] Toggle disable on web → `socialhub skills list` shows `Disabled` status

---

## Notes For Claude Code

- The repo has unrelated dirty changes outside this work. Do not revert them.
- Work only in `socialhub/` for CLI changes.
- Backend and frontend are Codex's responsibility.
- CLI implementation of login/logout/sync is already complete — see `socialhub/cli/skills/store_client.py` and `socialhub/cli/commands/skills.py`.
