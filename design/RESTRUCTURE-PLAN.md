# Project Restructure Plan

## Overview

Three goals:
1. Rename Python package `socialhub` → `cli` (flatten `socialhub/cli/` into `cli/`)
2. Reorganize root directory — group CLI code, move Web code, archive unused files
3. Standardize all file and directory naming conventions

---

## 1. Directory Changes

### Before → After

```
Before                              After
──────────────────────────────────  ──────────────────────────────────
Socialhub-CLI/                      Socialhub-CLI/
├── socialhub/                      ├── cli/                   ← renamed + flattened
│   └── cli/                        │   ├── __init__.py
│       ├── __init__.py             │   ├── main.py
│       ├── main.py                 │   ├── config.py
│       ├── config.py               │   ├── commands/
│       ├── commands/               │   ├── skills/
│       ├── skills/                 │   ├── api/
│       ├── api/                    │   ├── local/
│       ├── local/                  │   └── output/
│       └── output/                 │
├── tests/                          ├── tests/                 ← stays, moved under cli/ dir
├── pyproject.toml                  ├── pyproject.toml         ← updated
├── frontend/                       ├── skills-store/
│                                   │   ├── backend/           ← unchanged
├── skills-store/                   │   ├── frontend/          ← moved from root frontend/
│   ├── backend/                    │   ├── alembic/
│   └── alembic/                    │   └── render.yaml
│                                   │
├── docs/          (HTML only)      ├── design/                ← NEW: all .md docs
│                                   ├── CODEX.md               ← stays at root
├── examples/                       ├── README.md
├── render.yaml    (duplicate)      └── old/                   ← archived unused files
├── CODEX.md                            ├── docs/              ← entire docs/ archived
├── docs/                               ├── examples/
└── README.md                           └── ...
```

**Key flattening:** `socialhub/cli/main.py` → `cli/main.py`
The inner `cli/` subdirectory is eliminated; its contents become the `cli` package directly.

---

## 2. Import Path Changes

All imports change from `socialhub.cli.xxx` → `cli.xxx`

| Before | After |
|--------|-------|
| `from socialhub.cli.main import app` | `from cli.main import app` |
| `from socialhub.cli.config import load_config` | `from cli.config import load_config` |
| `from socialhub.cli.commands import ...` | `from cli.commands import ...` |
| `from socialhub.cli.skills.security import ...` | `from cli.skills.security import ...` |
| `from socialhub.cli.skills.sandbox import ...` | `from cli.skills.sandbox import ...` |
| `from socialhub.cli.local.reader import ...` | `from cli.local.reader import ...` |
| `from socialhub.cli.local.processor import ...` | `from cli.local.processor import ...` |
| `from socialhub.cli.api.mcp_client import ...` | `from cli.api.mcp_client import ...` |

### Files that need import updates (8 files)

| File | Lines to change |
|------|----------------|
| `cli/__init__.py` | `from socialhub.cli import __version__` |
| `tests/test_cli.py` | `from socialhub.cli.main import app` |
| `tests/test_config.py` | `from socialhub.cli.config import ...` |
| `tests/test_local_reader.py` | `from socialhub.cli.local.reader import ...` |
| `tests/test_processor.py` | `from socialhub.cli.local.processor import ...` |
| `tests/test_sandbox.py` | `from socialhub.cli.skills.sandbox import ...` |
| `tests/test_security.py` | `from socialhub.cli.skills.security import ...` |
| `cli/skills/store/report-generator/main.py` | `from socialhub.cli.config import ...` etc |

---

## 3. pyproject.toml Changes

```toml
# Before
[project.scripts]
sh = "socialhub.cli.main:cli"
socialhub = "socialhub.cli.main:cli"

[tool.setuptools.packages.find]
include = ["socialhub*"]

[tool.pytest.ini_options]
addopts = "-v --cov=socialhub --cov-report=term-missing"

# After
[project.scripts]
sh = "cli.main:cli"
socialhub = "cli.main:cli"          ← command name stays "socialhub" (user-facing, no change)

[tool.setuptools.packages.find]
include = ["cli*"]

[tool.pytest.ini_options]
addopts = "-v --cov=cli --cov-report=term-missing"
```

> Note: The terminal command `socialhub` (what users type) stays unchanged.
> Only the internal Python import path changes.

---

## 4. Files Moved to `old/`

| File/Folder | Reason |
|-------------|--------|
| `render.yaml` (root) | Duplicate of `skills-store/render.yaml` |
| `TO-CC.md` | Stale Codex handoff note |
| `Heartbeat.md` | Runtime-generated file |
| `Memory.md` | Runtime-generated file |
| `QA.md` | AI agent internal tool file |
| `User.md` | AI agent profile file |
| `consulting_demo_report.md` | Demo run output |
| `demo_business_report.md` | Demo run output |
| `Doc/` (entire folder) | Generated reports from demo runs |
| `data/` | Demo CSV data |
| `memory/` | Runtime AI memory |
| `socialhub_cli.egg-info/` | Build artifact |
| `docs/` (entire folder) | GitHub Pages site no longer maintained; HTML prototypes replaced by React |
| `examples/` | Sample skill package not needed at current stage |

---

## 5. Files Moved to `design/` (with rename)

Currently scattered across `docs/` with inconsistent naming. All moved to `design/` and renamed to `kebab-case`:

| Before | After |
|--------|-------|
| `docs/DESIGN.md` | `design/architecture.md` |
| `docs/PRD-Skills-Store.md` | `design/prd-skills-store.md` |
| `docs/README.md` | `design/overview.md` |
| `docs/SECURITY-GUIDE-DEVELOPERS.md` | `design/security-guide-developers.md` |
| `docs/SECURITY-GUIDE-USERS.md` | `design/security-guide-users.md` |
| `docs/SKILLS-DEVELOPMENT-PLAN.md` | `design/skills-development-plan.md` |
| `docs/TASKS-SKILLS-STORE.md` | `design/tasks-skills-store.md` |
| `docs/skills-store-design.md` | `design/skills-store-design.md` ✓ |
| `docs/skills-store-engineering-guidelines.md` | `design/skills-store-engineering-guidelines.md` ✓ |
| `docs/skills-store-implementation-plan.md` | `design/skills-store-implementation-plan.md` ✓ |
| `docs/skills-store-render-deploy.md` | `design/skills-store-render-deploy.md` ✓ |
| `docs/skills-technical-spec.md` | `design/skills-technical-spec.md` ✓ |
| `docs/storefront-user-cases.md` | `design/storefront-user-cases.md` ✓ |
| `design/RESTRUCTURE-PLAN.md` (this file) | `design/restructure-plan.md` |

---

## 6. Naming Conventions

### Rules

| Type | Convention | Example |
|------|-----------|---------|
| Directories | `kebab-case` | `skills-store/`, `report-generator/` |
| Python files | `snake_case.py` | `store_client.py`, `user_skill.py` |
| React components | `PascalCase.jsx` | `SkillCard.jsx`, `UserPage.jsx` |
| React utilities/lib | `camelCase.js` | `api.js`, `session.js` |
| Design docs | `kebab-case.md` | `prd-skills-store.md` |
| Root prominent files | `UPPER-CASE.md` | `README.md`, `CODEX.md` |
| Config files | keep as-is | `pyproject.toml`, `render.yaml`, `vite.config.js` |

### Impact of naming changes

**`design/` docs** (13 files renamed, no code impact — these are documentation only):
- No imports, no references in code
- Only `CODEX.md` references `docs/TASKS-SKILLS-STORE.md` → update path to `design/tasks-skills-store.md`

**No other naming changes required:**
- Python files in `cli/` already use `snake_case` ✓
- React files in `skills-store/frontend/` already use correct conventions ✓
- Directory names are already `kebab-case` ✓

---

## 7. Deployment Impact

| Area | Impact |
|------|--------|
| **Render (backend)** | None — `skills-store/backend/` unchanged |
| **GitHub Pages** | Site goes offline — `docs/` moved to `old/`. Intentional. |
| **CLI install** | Re-run `pip install -e .` after rename. Terminal command `socialhub` still works. |
| **CI/CD** | Update any pipeline referencing `socialhub/` path or `--cov=socialhub` → `cli/` |
| **Existing installed CLIs** | Must reinstall: `pip install -e .` from project root |
| **Frontend dev server** | Path changes: run `npm` commands from `skills-store/frontend/` instead of `frontend/` |

---

## 8. Execution Order

1. Create `old/` directory (already have `design/`)
2. Move files/folders to `old/`
3. Move + rename `.md` docs from `docs/` → `design/`
4. Move entire `docs/` → `old/docs/`
5. Move entire `examples/` → `old/examples/`
6. Move `frontend/` → `skills-store/frontend/`
7. Flatten `socialhub/cli/` → `cli/` (rename + restructure)
8. Update `pyproject.toml` (3 lines)
9. Update 8 import files
10. Update `CODEX.md` doc path reference
11. Re-run `pip install -e .`
12. Run `pytest` to verify
