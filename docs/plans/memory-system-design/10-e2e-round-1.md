# E2E Round 1 — Functional Correctness

**Date:** 2026-04-02  
**Focus:** Core pipeline functional correctness  
**Verdict:** CONDITIONAL PASS — infrastructure sound, 10 BRs need Round 2 coverage

---

## Test Execution Results

### All checks passed (30/30)
- Import verification: all modules ✓
- Store full roundtrip (profile/insight/campaign/summary): ✓
- MemoryManager load→build→save pipeline: ✓
- CLI commands (status/set/list): ✓
- Token budget enforcement (503 within 650-token tolerance): ✓
- PII scan battery (7 cases including None/empty fix): ✓
- BR-02 archived campaign gating: ✓
- BR-04 low confidence insight gating: ✓
- BR-15 extractor timeout (mock slow caller, 1s timeout respected): ✓
- BR-06 summary_id returned to caller for notification: ✓

---

## Expert Review Findings

### Product Expert: 4/10
BRs covered: 4/15 fully (BR-02, BR-04, BR-06, BR-15)  
Missing: BR-03, BR-07, BR-08, BR-09, BR-10, BR-11, BR-12, BR-13, BR-14 (Linux CI)  
No performance timing, no fault-injection, no audit-trail tests

### Customer Expert: Key Risks
- Risk 1 (HIGH): Stale insight `⚠️ 超过30天` warning not tested
- Risk 2 (HIGH): `sh memory init` completely untested (first user touchpoint)
- Risk 3 (HIGH): LLM extractor real call path is all mocked (now BR-15 timeout added)
- Risk 4 (MEDIUM): PII in campaign goal text not scanned
- Risk 5 (MEDIUM): Windows 0o600 permission skip — actual data exposure on shared machines
- Risk 6 (MEDIUM): `sh memory clear --all` triple-confirmation untested
- Risk 7 (LOW-MEDIUM): Token tolerance overage compounding risk

---

## Round 1 Corrections Applied

| Item | Fix |
|------|-----|
| BR-15 timeout path | Added mock-slow-caller test: 1s timeout respected, result=None |
| BR-06 notification contract | Verified: manager returns summary_id; caller (main.py/ai.py) prints notification |
| pii.py None input | Already fixed in Phase 11 review |

---

## Round 2 Priorities

1. `sh memory init`, `sh memory show`, `sh memory delete`, `sh memory clear` commands
2. `sh memory list` default grouped view (BR-10)
3. TTL boundary conditions and count caps (BR-11)
4. Fault injection: corrupt YAML, permission denied
5. Performance timing (`load() ≤ 100ms`, `build_system_prompt() ≤ 50ms`)
6. `--no-memory` end-to-end: verify no file written (BR-13)
7. `save_insight_from_ai` pii_masked=True path in trace log
