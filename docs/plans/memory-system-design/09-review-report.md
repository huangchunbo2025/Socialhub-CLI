# Code Review Report — Memory Subsystem

**Date:** 2026-04-02  
**Baseline commit:** e0c46b18  
**Review scope:** 8 modified files + 8 new files  
**Reviewers:** 4 parallel agents (Architecture / Reliability / Performance / Hygiene)

---

## Fixed Issues

| ID | Severity | File | Fix Applied |
|----|----------|------|-------------|
| CRIT-1 | Critical | `cli/ai/client.py` | Removed throwaway `MemoryManager()` inside `call_ai_api`; replaced `memory_context` param with `system_prompt: str` — callers now pre-build via `mm.build_system_prompt()` |
| C-1 (reliability) | Critical | `cli/memory/store.py:115` | `_ensure_dirs` now logs `OSError` at WARNING instead of silent `pass` |
| C-3 (reliability) | Critical | `cli/memory/store.py:297` | `_prune_by_count` wraps `sorted(glob, key=stat)` in try/except to handle concurrent deletes |
| I-1 (reliability) | Important | `cli/memory/pii.py:44` | `scan_and_mask(None/empty)` now returns `("", False)` instead of `(None, False)` |
| IMP-3 (architecture) | Important | `cli/memory/injector.py` | Fixed L2/L3 cutting order: L3 now trimmed first before L2 is dropped; assembly order updated to L4→L3→L2 |
| I-4 (performance) | Important | `cli/memory/store.py:85` | `yaml.dump` → `yaml.safe_dump` |
| I-6 (hygiene) | Important | `cli/memory/store.py:33` | Removed unused imports: `ExtractionResult`, `InsightData` |
| M-3 (reliability) | Minor | `cli/memory/extractor.py:95` | `str.format(conversation=...)` → `str.replace("{conversation}", ...)` to avoid KeyError on `{…}` in user messages |
| dead import | Minor | `cli/memory/manager.py:10` | Removed unused `import hashlib` |
| duplicate import | Minor | `cli/memory/manager.py:148` | Removed duplicate `BASE_SYSTEM_PROMPT` import inside except block |
| get_status waste | Minor | `cli/memory/manager.py:338` | `get_status()` no longer loads all insights/summaries just to count; uses direct `glob("*.json")` |
| type_filter bug | Minor | `cli/commands/memory.py:70` | Fixed `(None, "profile", None)` → `(None, "profile")` |
| ambiguous name | Minor | `cli/commands/memory.py:106`, `cli/memory/injector.py:204` | Renamed `l` → `line` |
| unused import | Minor | `cli/ai/client.py:15` | Removed `BASE_SYSTEM_PROMPT` from import (unused after CRIT-1 fix) |
| callers updated | — | `cli/main.py`, `cli/commands/ai.py` | Updated to pre-build system prompt and pass as `system_prompt=` to `call_ai_api` |
| corrupt file logging | Minor | `cli/memory/store.py:218,255` | Added `logger.debug(...)` for skipped corrupt JSON files |

---

## Deferred / Won't Fix

| ID | Reason |
|----|--------|
| IMP-2 (duplicate MemoryConfig) | Python duck-typing makes it work at runtime; mypy type-mismatch is cosmetic. Fixing requires a broader config refactor out of scope for this PR. |
| IMP-6 (commands/memory.py private access) | Commands directly access `mm._store` for list/show/delete; adding public store accessors is a refactor deferred to a follow-up. |
| C-2 reliability (fixed tmp suffix) | Single-user CLI; concurrent write risk is theoretical. Changing suffix requires testing across Windows/POSIX path-handling edge cases. |
| I-2 architecture (MemoryContext no_memory field) | `no_memory` is passed as explicit arg; adding it to MemoryContext is schema change with no functional benefit now. |
| I-5 (MemoryConfig lower-bound validation) | Operators who set max_insights=0 get documented behavior; adding `ge=1` validators is safe but not urgent. |
| C-1 performance (purge on every load) | Amortization requires a sidecar timestamp file; deferred to Phase 2 performance work. |

---

## Test Results After Fixes

```
51 passed, 1 skipped in 16.74s
```

1 skipped: `test_file_permission_600` — POSIX permissions not enforced on Windows (expected).

---

## Ruff Lint

No actionable errors (F4xx, E7xx, Bxxx) in changed files. Pre-existing UP045/F401 in unchanged code not modified.
