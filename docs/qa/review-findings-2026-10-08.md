# Independent review findings and response

## First spec review
Reviewed tasks2–5 read-only. Four material issues reproduced by parent in tests/test_review_regressions.py, all failed before fixes:
1. Recall EVENT candidates blocked correct/forget. Excluded events from mutation candidates.
2. Same-second valid_from truncated windows. Microsecond precision preserved across9write paths; reopen history regression.
3. Snapshot exported EVENT interactions and inflated fact counts. Exclude event records from snapshot/stats; reject event snapshot imports.
4. Casefold fact equality conflated case-sensitive values. Exact repeat equality only.

Provider flag finding was stale by delivery: tests/test_live_browser already changed to MEMORY_BEDROCK0 explicitly. Added missing HTTP/inference saturation, delayed speaker/hour and provider daypart parity, concurrent reopen/replay assertions.

Parent full suite after response:120passed,1upstream SDK/settings warning. Spec re-review pending, then code-quality review. No reviewer self-report substituted for parent execution.
