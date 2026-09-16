# Frankenstein text repairs, clause alignment and provenance

16 September 2026. Follow-up to `ALIGNMENT_FIX_20260916.md`.

## Confirmed legacy text defects

The original was loaded from the legacy normalized HTML artifact (source reference
`manifests/../books/1.html`), not a newly uploaded EPUB. The stored normalized
artifact already contains detached drop-cap whitespace. The current HTML adapter
concatenates inline text without inserting spaces; regression tests now explicitly
cover `I` + `t`, `W` + `e`, `C` + `lerval`, and legitimate `I am` spacing.

The earlier source-QA cleanup repaired twelve initials but its regex required two
or more remaining letters. It missed `I t`, `W e`, `O n` and `M y`; frequency-only
recognition also missed `C lerval`. Source QA v3 permits one-letter remainders and
uses repeated in-book spelling evidence for rare joined names. It still proposes
corrections and does not silently alter incoming text.

User-authorized, audited corrections applied to the current local editions:

- Original: c8.p2, c11.p2, c12.p2, c13.p2, c14.p2, c17.p2, c29.p2, c30.p2.
- B2: c13.p2 (`O n` → `On`). Other affected original openings were already joined
  or rewritten correctly in B2.
- Ukrainian: corresponding openings inspected; no detached-initial defect or
  lost first-word meaning found in these passages. This is not whole-book fidelity
  certification. No Ukrainian text was changed or regenerated.

Nine `ContentBlockRevision` records retain before/after text and the repair note.
Original and B2 sentence/lexical/source-QA refreshes used the normal revision path.
Text-dependent artifacts are invalidated; old paid analyses are not relabelled as
current when their input changed. No paid analysis or generation was triggered.

## Offline matching and semicolon clauses

LaBSE is an explicit local-model option on the staff alignment preview; MiniLM
remains available. Model identity is part of job/cache versioning. The UI defaults
its selector to LaBSE; the general block/chapter embedding configuration is unchanged.

A real-model comparison on 12 difficult original/Ukrainian paragraphs improved
accepted coverage in nine, tied in three, with no decrease in accepted groups.
Examples: c10.p4 went from 10/14 to 14/14 accepted sentence groups; c8.p2 from 6/8
to 8/8. These are coverage observations, not calibrated accuracy measurements.
LaBSE model card: https://huggingface.co/sentence-transformers/LaBSE (256-token
window, sentence-transformers implementation). Both models run locally; neither
uses a paid generation API.

`offline-sentence-v5` refines accepted sentence groups at semicolons. The resulting
clause spans use the original Unicode code-point offsets, preserve punctuation and
whitespace, and never rewrite prose or stored sentence splitting. A refinement is
used when at least two smaller mappings are accepted and no clauses are unmatched.
Uncertain clauses remain plain text inside their paired paragraph; they do not
suppress independent confident clause highlights. Otherwise the broader sentence
group remains. Uncertain original sentence mappings remain uncertain.
This is clause correspondence, not word-by-word translation equivalence.

The existing parallel schema's `primary_sentences` / `secondary_sentences` arrays
carry the actual display units (sentences or clauses) for that artifact. Group
indexes reference those arrays. Both arrays and groups invert together. Existing
backend rendering already consumes validated spans and indexes and does not infer
linguistic sentence boundaries. Added `alignment_provenance` describes the exact
artifact/model/version/segmentation; missing or changed inputs expose no current
artifact. No authentication, publication or client transport change is required.

## Staff passage provenance

The editable reader and alignment preview now include expandable passage details:
current text SHA-256, source reference, generation model/prompt/run where recorded,
source revision at generation where recorded, and latest audited edit separately.
The preview additionally shows alignment artifact, pipeline run, model, algorithm,
segmentation and input hash. Missing records are labelled, never guessed.

Legacy Ukrainian generation stored a model per block but not an AI-run link. Its
single successful matching edition-level translation run is shown explicitly as
an edition-level record; it is not presented as a stored passage link. New
translations now retain their exact AI-run ID and prompt version per block.

## Verification so far

The full 347-test suite passed before the final reverse-direction selection test;
that additional test and the full alignment test module passed afterwards.
New-translation provenance assertions also pass in the translation test module.
Ruff lint/format, migration drift and Django system checks pass. The live worker's
real `wordfreq` scan, replaying the eight original pre-repair passages in memory,
now detects all eight at 0.98 confidence, including the recurring name Clerval.

Both staff views rendered current database text with an unsaved staff principal
and returned 200. Original c11.p2 shows the new audited revision; Ukrainian c11.p2
shows `gpt-5.6-terra`, `literary-block-translation v1`, and its edition-level record
scope. Existing edits to Ukrainian remain preserved and visible separately.


## Completed runs and final refresh

The initial v4 full-book runs completed, 815 blocks each:

| Pair | Model | Highlight groups (including clauses) | Entirely paragraph-only | Unmatched units |
| --- | --- | ---: | ---: | ---: |
| Original → Ukrainian | LaBSE | 4,552 | 4 | 2 |
| B2 → Ukrainian | LaBSE | 3,928 | 14 | 3 |
| B2 → original | MiniLM | 4,481 | 2 | 2 |

Subsequent independent Ukrainian edits/re-segmentation and publication occurred
while this session was paused. Those changes are preserved; 169 original/UK
artifacts no longer matched the current inputs when work resumed. These counts
therefore describe the completed v4 runs, not current coverage after later edits.

The Chapter V skin/hair/teeth passage revealed an overly conservative refinement
rule: one uncertain clause suppressed all independent fine matches. V5 permits
confident clauses to highlight while keeping uncertain clauses plain. LaBSE's
current four clause scores are 0.8438, 0.8810, 0.7069 and 0.8849. Skin, hair and
the final contrast qualify; the teeth clause is not forced above the threshold.
V5 refreshes are queued against current texts after the final rebuild. No new paid
calls or publication operations were performed by this task.

Final validation: 353 tests passed, Ruff lint/format, migration and system checks
passed; web and worker rebuilt/restarted. Queued v5 run IDs:

- Original → Ukrainian: `33e3139c-4f52-418b-a3fc-504898536e81`.
- B2 → Ukrainian: `9ee73dec-31a3-49d6-a6cf-b31e5795458d`.
- B2 → original: `cf694167-46ef-4dca-bb33-0ed83b6a7653`.

The owner requested a quick handoff to conserve budget. These final refreshes
continue asynchronously; their final coverage is not asserted here. Existing
unrelated toolbar/CSS/detail-page edits are left uncommitted for their author.
