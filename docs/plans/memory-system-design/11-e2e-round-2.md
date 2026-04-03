# E2E Round 2 — Quality & UX

**Date:** 2026-04-02  
**Focus:** Performance, fault tolerance, BR-11/BR-13  
**Round 2 Score (Product):** 6/10 | (Customer): 5/10

---

## What Was Verified

| Item | Result |
|------|--------|
| Performance: load() | 47ms ✓ (SLA ≤100ms) |
| Performance: build_system_prompt() | 0.2ms ✓ (SLA ≤50ms) |
| BR-11: TTL + count cap | 2 expired + pruned, remaining≤5 ✓ |
| BR-13: --no-memory writes nothing | 0 files written ✓ |
| Fault: corrupt YAML | Graceful fallback ✓ |
| Fault: corrupt JSON insight | Silently skipped with debug log ✓ |
| Test suite | 60 passed, 1 skipped ✓ |

## Fix Applied in Round 2

`purge_expired()` moved to daemon thread in `manager.py::load()` — load time dropped from 132ms → 47ms on Windows.

## Still Uncovered (Critical for Release)

- `sh memory init` flow (BR-08, BR-09) — first user touchpoint, entirely untested
- BR-03: memory annotation `[memory: ...]` ID ↔ `sh memory list` ID consistency
- BR-05: PII hit terminal notification (dim line printed, not just file-skipped)
- BR-07: `update-campaign` immutability of created_at/campaign_id
- BR-10: `sh memory list` default grouped view
- BR-14: 0o600 file permission (Windows skip — no Linux CI path)
- PII in campaign goal text field not scanned

## Round 3 Priorities (Top 3)

1. `sh memory init` + campaign commands (`add-campaign`, `update-campaign`)
2. BR-03 ID consistency + BR-05 PII terminal notification
3. PII in business context / campaign goal freeform fields
