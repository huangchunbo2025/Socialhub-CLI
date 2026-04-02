# Code Review Report — SocialHub CLI Advancement

**Date**: 2026-03-31
**Reviewers**: Architecture × Reliability × Security × Performance (4 parallel agents)
**Baseline commit**: d003968e0136a242a8afd3652836f9c2ab642e0f
**Branch**: feat/cli-advancement

---

## Summary

| Category | CRITICAL | IMPORTANT | MINOR | Fixed |
|----------|----------|-----------|-------|-------|
| Architecture | 4 | 8 | 5 | 6 |
| Reliability | 4 | 7 | 6 | 4 |
| Security | 4 | 7 | 8 | 4 |
| Performance | 4 | 5 | 4 | 0 |
| **Total (dedup)** | **8** | **15** | **12** | **10** |

---

## Fixed Issues

| ID | File | Issue | Fix Applied |
|----|------|-------|-------------|
| C-API-1 | `cli/ai/client.py:83,102` | Bare `httpx.post` bypassed enterprise proxy/CA | Replaced with `httpx.Client(**build_httpx_kwargs())` |
| C-AI-2 | `cli/commands/ai.py:37` | `sh ai chat` bypassed sanitizer | Added `validate_input_length` + `sanitize_user_input` |
| C-ZIP-1 | `cli/commands/skills.py:307` | Zip slip — `extractall()` unvalidated | Added per-member path validation before extraction |
| C-SESS-1 | `cli/ai/session.py:74` | Path traversal denylist incomplete | Replaced with allowlist regex `^[A-Za-z0-9_-]{1,80}$` |
| C-THR-1 | `cli/ai/client.py:132` | Non-daemon thread blocks on SIGINT, no join timeout | Added `daemon=True` + `join(timeout=65)` in `finally` |
| C-ERR-1 | `cli/ai/client.py:183` | Raw API error body leaked subscription/internal details | Extracts `error.message` only, caps at 200 chars |
| I-TRC-1 | `cli/commands/trace_cmd.py:64,66` | Field names `step_num/total_steps/success_count` didn't match writer | Fixed to `step/total/succeeded` |
| I-WARN-1 | `cli/commands/skills.py:313` | Dev-mode warning printed after extraction | Warning displayed before extraction completes |
| C-PATH-2 | `cli/ai/session.py:load/clear` | `ValueError` from invalid ID not caught | Wrapped `_session_path()` calls in try/except |
| TEST-1 | `tests/test_session.py` | Path traversal test only checked one variant | Added 3 variants + valid ID format test |

---

## Remaining Known Issues (not fixed — tracked)

### IMPORTANT — Deferred

| ID | File | Issue | Reason Deferred |
|----|------|-------|-----------------|
| I-TRACE-WIRE | `cli/main.py`, `cli/ai/executor.py` | `TraceLogger` never called; trace file always empty | Requires cross-cutting changes to main execution path; deferred to next iteration |
| I-NOPROXY | `cli/network.py` | `no_proxy` field captured but not passed to httpx | httpx `no_proxy` support requires `mounts` API; deferred |
| I-SSLWARN | `cli/network.py:32` | `ssl_verify=False` no operator warning | Deferred — low risk with config-driven access |
| I-SCHEMA-1 | `cli/ai/session.py` | Session schema uses Unix float timestamps, missing `expires_at` | Schema evolution; backward compatible; deferred |
| I-SYSAR | `cli/main.py:243` | Session ID parsed via `sys.argv` instead of `ctx.obj` | Complex Typer context threading; partial workaround in place |
| I-TRACESHOW | `cli/commands/trace_cmd.py` | `trace show` and `trace stats` not implemented | PRD feature gap; deferred to follow-up |
| I-CIRCUIT | `cli/ai/executor.py:199` | Circuit breaker per-invocation (not persistent) | Cross-plan persistence needs singleton; tracked |
| I-CONFIG | `cli/ai/executor.py:18-19` | Guard-rail constants hardcoded, not in `AIConfig` | Config model expansion needed; deferred |

### MINOR — Accepted

- `execute_plan()` is 96 lines (>50 guideline) — low risk, well-structured
- `_install_local_skill()` is 83 lines — extraction helpers would improve readability
- Trace rotation has stat→rename TOCTOU window — low severity, no security impact
- `Session.is_expired()` measures from `created_at` not `last_active` — documented behavior

---

## Test Results

```
352 passed, 2 skipped (POSIX permissions on Windows)
```

All new test files:
- `tests/test_sanitizer.py` — 10 tests
- `tests/test_formatter.py` — 18 tests
- `tests/test_trace.py` — 25 tests (24 pass, 1 skipped Windows)
- `tests/test_session.py` — 15 tests (14 pass, 1 skipped Windows)
- `tests/test_network.py` — 8 tests

---

## Confirmed Architecture Strengths

- `_BoundedTTLCache` — thread-safe LRU+TTL, correct thundering-herd mitigation
- `TraceLogger._write()` — TOCTOU-safe `os.open(O_CREAT, 0o600)`, correct
- `SessionStore.save()` — atomic tmp→replace write with `0o600` permissions
- `OutputFormatter` — stdout/stderr separation correctly enforced
- `executor.py` — all three CLAUDE.md red lines satisfied (shell=False, char validation, validator call)
- `network.py` — clean `build_httpx_kwargs/build_httpx_client` split, reusable with AsyncClient
