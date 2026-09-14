# Difficulty calibration fixtures

The initial matrix is `tests/fixtures/calibration/difficulty-v1.json`: twelve
original AI-authored snippets covering EN/DE/UK × letter/dialogue/archaic/
contemporary prose. They include language-specific quotation marks, apostrophes,
line breaks, German separable verbs and Unicode outside the BMP. They exercise
the structured-output and citation pipeline. They are **synthetic, unrated
fixtures**, not authentic literary passages, human judgments or proof of model
quality. Historical pastiche particularly needs fluent-reader review.

Validate the corpus and print its exact input hashes without credentials,
database access, model downloads or paid calls:

```bash
.venv/bin/python manage.py check_calibration tests/fixtures/calibration/difficulty-v1.json
```

This prints JSON to stdout. It does not write files, import editions, queue jobs
or modify editorial levels. The fixture directory is repository test data and
is not copied into the production image; pass your own accessible fixture path
when invoking the command inside a container.

## Preparing a reference set

1. Add actual edition excerpts covering the same languages and categories, with
   `source_kind: "catalog_excerpt"`. Record work, edition/provenance, chapter,
   block IDs, exact excerpt boundaries and whether wording is machine-generated
   in `source_note`. Preserve text exactly. Export only approved public material;
   private imports must not become a shared fixture corpus. The ignored legacy
   `build/` directory is not a reproducible CI dependency.
2. Have a fluent human reviewer assess the excerpt without seeing the model's
   predicted level. Fill `reference` only when that review actually exists:

   ```json
   {
     "cefr": "B2",
     "reviewer": "Reviewer identifier",
     "rationale": "Specific vocabulary, syntax and discourse evidence",
     "reviewed_on": "2026-09-14"
   }
   ```

   This is the metadata format, not a supplied B2 reference. Keep unreviewed or
   unresolved examples at `null`. The validator cannot authenticate a reviewer
   or establish the reliability of a rating; that is part of corpus review.
3. Keep the original synthetic matrix separate from the authentic reference set.
   Short excerpts are sample-level fixtures, not full-chapter/book ground truth.
   Include varied difficulty and unfamiliar content; do not infer levels merely
   from date, genre, vocabulary frequency or sentence length.
4. Validate the resulting file to obtain `fixture_inputs`. Hashes cover language,
   exact block IDs, order and text, including whitespace. Rating and category
   edits do not require rerunning the model; text edits do.

## Comparing saved predictions

Supply a separate JSON file with this shape:

```json
{
  "schema_version": 1,
  "predictions": [
    {
      "sample_id": "en-letter",
      "input_hash": "<64-character hash from fixture_inputs for the analyzed text>",
      "provider": "provider-name",
      "model": "exact-model-name",
      "prompt_version": "2",
      "processor_version": "chapter-analysis-v2",
      "status": "succeeded",
      "cefr": "B2",
      "input_tokens": 1000,
      "output_tokens": 200,
      "estimated_cost_usd": "0.001"
    }
  ]
}
```

The values above illustrate the format; they are not measurements. The hash
placeholder must be replaced with the fixture hash, **not** the production
AIRun window hash (which covers a different input envelope). Ensure each saved
prediction actually assessed the matching fixture text. Failed outcomes use
`status: "failed"` and `cefr: null`. Unknown tokens/cost are `null`, not zero.
Each row is one final evaluation outcome per sample/configuration; consolidate
its billed attempts into the usage fields. Separate repeated trials into
separate prediction files rather than double-counting the same sample.

```bash
.venv/bin/python manage.py check_calibration tests/fixtures/calibration/difficulty-v1.json --predictions /tmp/predictions.json
```

The report groups by provider/model/prompt/processor version. It includes:

- submitted/succeeded/failed/missing counts and unrated sample IDs;
- exact agreement, within-one-band agreement and mean absolute band error,
  calculated only from successful predictions with a reference rating;
- individual comparisons with language/category and two-or-more-band review
  cases, for examining failures rather than hiding them in one score;
- reported token/cost totals, including failed outcomes, plus unknown-usage
  counts. These subtotals are not complete billing totals when usage is unknown.

With no rated predictions, agreement/error metrics are `null`. Unknown sample
IDs, stale text hashes and duplicate sample/configuration outcomes are rejected.
Model confidence is not used as a substitute for measured agreement. The tool
compares saved results only; paid calibration execution is not added here.

## Remaining P1-3 work

The fixture matrix, schema, offline comparison and multilingual citation tests
are implemented. Authentic EN/DE/UK reference excerpts, human ratings, actual
model measurements, and corpus-derived first-encounter vocabulary remain open.
Do not mark P1-3 calibrated merely because these plumbing tests pass.
