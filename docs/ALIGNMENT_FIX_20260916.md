# Ukrainian–English sentence alignment, 16 September 2026

The original-English → Ukrainian v2 run `9b341b89` completed all 815 blocks.
It exposed 2,138 highlightable groups, including 149 inherited single-sentence
paragraphs. Ten paragraphs fell back before inference because a sentence exceeded
the encoder window. Another 30 paragraphs had no groups above the 0.82 threshold.
A successful job therefore did not mean every sentence was highlighted.

`offline-sentence-v3` retains the configured MiniLM model and adds:

- Token-checked splitting of long sentences at whitespace where possible, with
  token-count-weighted pooling and normalization. Every chunk includes its special
  tokens in the window check; no sentence suffix is silently truncated. Sentence
  offsets remain unchanged. Paragraph size limits still bound work.
- Additional acceptance for DP-selected 1:1 matches scoring at least 0.75 when
  their cosine beats every other single-sentence candidate on both sides of the
  paragraph by at least 0.10. Existing 0.82 acceptance remains. This is a heuristic,
  not calibrated confidence; merged groups retain the stricter rule. This margin
  compares individual alternatives, not complete competing DP paths.
- Explicit paragraph fallback reasons, uncertain matched-group counts, and
  unmatched-sentence counts in the job summary and staff preview.

The version change invalidates cached sentence highlights. All three existing
Frankenstein pairs were queued again using the normal Celery worker. No paid API
calls, text edits, editorial approval or publication are part of this operation.
LaBSE was not adopted without a real quality comparison, and these changes do not
promise complete alignment or word/phrase correspondence.

Validation: full offline unit suite, Ruff lint/format, migration drift and Django
system checks. Unit tests use fake embeddings/tokenization and establish logic,
not multilingual model quality. Real-model results are recorded below separately.

## Real-model verification

Original EN → Ukrainian run `1c87b2be-3704-4fea-9fde-9b408a1093ad` succeeded:
815 blocks, 2,767 highlightable groups (previously 2,138), 19 entirely paragraph-only
blocks (previously 40), 509 uncertain matched groups, 18 unmatched sentences across
both sides. All 19 paragraph-only blocks are low-confidence cases; there are no
size/token/missing-sentence fallbacks in this run.

All ten previously token-limited paragraphs now have highlights: c1.p8, c8.p7,
c10.p4, c14.p33, c16.p2, c18.p13, c24.p19, c27.p47, c28.p37 and c30.p6.
This does not mean every sentence in those paragraphs is accepted.

Inspected 21 newly accepted reciprocal-margin pairs across chapters 1, 10, 20 and
30, including the reported Scotland sentence: counterparts match in meaning.
This is a spot check, not a whole-book bilingual accuracy assessment. Staff view
rendering with an unsaved staff principal returned 200 and included the new counts
and fallback breakdown; this does not test browser login or click interactions.

Both B2 refreshes also succeeded across 815 blocks each:

| Pair | Run | Highlightable groups | Paragraph-only blocks | Uncertain groups | Unmatched sentences |
| --- | --- | ---: | ---: | ---: | ---: |
| B2 → Ukrainian | `87e338c1-4603-4dbb-b43f-93070fc1acba` | 2,652 | 26 | 608 | 68 |
| B2 → original | `cc144a14-0c07-41c0-a141-7faf88693662` | 3,383 | 2 | 57 | 2 |

All remaining paragraph-only blocks in these runs are low-confidence cases.
The full suite passed 341 tests. Web and worker were rebuilt/restarted with
`docker compose up -d --build web worker`; `/healthz/` returned 200 afterwards.
