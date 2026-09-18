# Morning brief — 18 September 2026

B2 is the supported floor for Frankenstein with our current tools and fidelity rules.
The blind Luna judge separated B1 controls from published B2; originals were C1 except IV (B2).
Terra v5 at high reasoning still produced B2 on all three sampled passages, with seven minor fidelity findings.
Across five prompt versions, 13 completed generations judged B2; two interrupted attempts have unknown outcomes.
No whole-book B1 was generated or published. [Evidence and alternatives](ADAPTATION_PILOT.md#decision-after-judge-controls--18-september-2026).

## Current checkpoint

Processor commit `a20ca38` localizes non-English chapter analysis and private-import
blurbs and validates generated analysis/metadata prose offline. All 423 tests,
ruff checks, migration check and Django check passed. English judge v3 remains
unchanged; non-English analysis uses v4. Language detection is statistical and
rejects uncertain prose; it is not a fluency certificate.

The local processor rebuild and budgeted Ukrainian Luna rerun are in progress.
Stored Ukrainian analysis was English; its separate reader descriptions were
already Ukrainian. Backend and Angular verification is **not yet complete**.
[Ukrainian reader](http://localhost:9999/reader/shelley-frankenstein-uk-parallel)
will be the live check; local backend was down and is being restarted.

Night spend recorded so far: **$0.012511 / $10**. Next analysis batch has a $0.30
reserve, with a budget check before every paid request; no premium model calls.
The updated [parallel assessment](PARALLEL_READING_NEXT.md) and final cross-client
CEFR audit are still pending at this checkpoint; older findings there are not a
claim that tonight's assessment is complete.

Astra decides: production publication, French editorial review, and whether a
materially different B1 strategy or matched B1 source is worth a new experiment.
Recommended product direction: honestly labelled B2 with Ukrainian reader aids.
