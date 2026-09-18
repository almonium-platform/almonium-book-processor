# B2 chapter pilot

## Full-book generation

The source edition page now also offers **Generate / resume full B2 book (paid)**.
This creates a separate same-language `adaptation` edition with explicit source
lineage and `parallel_role=parallel`. It uses the current versioned pilot prompt
(v4), including the user's fidelity improvements and word-diff review.

Generation is a worker job with up to three requests in flight. Chapters larger
than 40,000 characters / 100 blocks are split at block boundaries; a single
oversized block is refused before creating the edition. Blank-only chunks and
empty chapters are preserved without AI requests. All blocks, media attributes,
chapter order/roles and canonical alignment groups are retained. Generation
decisions and AI-run IDs are stored on the derived blocks.

Completed chunks are checkpoints owned by the new edition (including their
spend), and failed retries reuse successful results. A failed chunk leaves no
partial normalized book: all chapters/blocks materialize in one transaction only
after completeness and source-revision checks. The parent job records progress;
the existing retry button resumes adaptation, never translation. A new source
revision or generation specification creates a new edition, not an overwrite.
Running jobs interrupted during a paid call still require operator reconciliation.

The completed draft stays **Needs review**, with a mandatory fidelity/difficulty
warning and `auto_publish=false`. The requested B2 level lives in generation
metadata; the editorial `cefr_level` remains unset. A by-construction alignment
run records the inherited groups, then the worker splits sentences, computes
vocabulary and queues paid difficulty reassessment on the generated wording.
None of these operations change the source edition. The existing staff reader
can show the full draft beside its original; chunk review pages retain the word
diff and change reasons.

This remains a reviewed-library workflow, not private-import adaptation. No
public API contract, backend or client deployment changes are part of this slice.
Human fidelity review, source-import cleanup and confirmation of the achieved
level are still required before manually publishing the draft.

### Full Frankenstein draft — actual result, 2026-09-14

- Edition: `shelley-frankenstein-en-orig-b2`
  (`f0617488-6553-4131-9a13-2e470a62ffa9`).
- Generation run: `d9b46765-3568-4cf0-b826-79fa51507e30`, prompt v4.
- 31 successful chunks, all 30 chapters and 815 blocks; 123 blocks kept
  verbatim. 76,419 whitespace-delimited words. All source block IDs and
  alignment groups match exactly, and the original source revision is unchanged.
- Generation estimate $1.923042; difficulty reassessment $0.067073;
  total for this full draft **$1.990115** (prior chapter pilots excluded).
- Sentence splitting, inherited alignment and vocabulary completed. The
  reassessment completed all 32 windows. Full staff parallel-reader rendering
  was checked on Chapter V.
- **Target not yet achieved by the estimator:** 9 chapters B2, 21 chapters C1;
  the aggregate is C1. The original roles were preserved, including introduction
  and preface currently marked as body; excluding those two would not change
  this conclusion. These remain model judgments, not validated ground truth.
- The draft remains Needs review, editorial level unset, and unpublished.

Editorial spot checks: the full Chapter V now unpacks the opening syntax,
preserves “now that I had finished”, “promised yourself”, the dehumanizing
“object”, and “my first thought would not fly towards”. But Chapter IV still
contains “Whence” and formal embedded scientific argument. Other flagged
chapters retain long abstract sentences. Some assessment evidence is weak
(metaphor, tragic content and literary references do not by themselves prove
C1), so do not blindly rewrite everything cited by the judge.

Next useful delivery: targeted revision of the still-difficult chapters using
specific reading barriers, with fidelity checked against the original and
already-suitable generated chapters retained. Reassess revised wording, not
just a new B2 label. Do not insert mandatory C1 modernization, regenerate the
entire book merely to change a badge, or publish this draft as proven B2.

Product decision, 2026-09-14: preserve Frankenstein's original C1 edition and
adapt directly to B2. Do not create a mandatory modernized C1 intermediate.
The analysis flag “modernization may help” is advisory, not an instruction to
generate another edition. Old-fashioned wording alone is not a defect.

On a public edition page, **Try a B2 chapter adaptation** queues one paid
worker request. The result page shows original/adapted paragraphs side by side,
keep/adapt decisions, change reasons, warnings, tokens and estimated cost.
B2 is a requested target, not a verified assessment. Nothing changes the original
text, CEFR, status or publication. The pilot is a saved AIRun result, not a
partial Edition, and cannot appear in the public catalogue or be published.

The prompt preserves accessible wording exactly, permits sentence splitting
within blocks, and forbids summarization, additions and contemporary retelling.
Headings and verse are protected. Block IDs and canonical groups are retained in
the source snapshot for later materialization. Completeness checks establish
structural correspondence, not semantic fidelity; review the actual output.

## Execution and safety

- Public catalogue only; staff authentication and POST required to queue.
- One chapter, at most 100 blocks / 40,000 source characters; 20,000 output-token
  ceiling. Larger chapters need windowed generation before full-book support.
- Uses the existing quality translation model setting and direct provider
  adapter, but a separate `level_adaptation` model configuration and prompt.
  Costs use the existing quality-tier price estimate, not verified invoices.
- Hash includes actual source text/structure, metadata, request/model/schema,
  prompt version and processor version. A repeat click reuses the same result.
- Failed retries create new ledger attempts; prior spend/results remain. If a
  saved completed response now passes local validation, it is reused without a
  provider call or double-counting its spend. Keep/adapt labels are derived from
  exact text comparison; incorrect model labels become review notes, not a
  reason to discard an otherwise valid paid chapter.
- Atomic queued→running claim prevents duplicate worker deliveries from paying
  twice. If a worker dies mid-call, an operator must reconcile that running job
  before retrying; no blind automatic paid retry. Broker dispatch failures may
  require re-enqueueing the existing queued task by its run ID.
- Raw response/usage is saved before validation. Edited sources reject stale
  completion. Removed sources keep scrubbed tombstone-linked spend, not text.
  A later edit marks the comparison stale at read time and leaves its saved
  original snapshot available for historical comparison.
- OpenAI Docs was used to check the existing adapter's
  [structured-output format](https://platform.openai.com/docs/guides/structured-outputs).
  Schema conformance does not verify meaning or CEFR.

## Next delivery

1. Read the real Chapter V pilot for clarity, omissions, semantic drift and voice.
2. Resolve source-import defects separately, with existing audited correction
   tools; do not silently rewrite the original as part of adaptation.
3. Review the complete generated B2 draft and its difficulty reassessment.
   Full-book generation is now implemented (see above); the chapter pilot is
   still not a publishable edition.
4. Confirm the full edition's level and fidelity before manual publication.
   The staff reader already supports original/B2 comparison via inherited groups.
   B1 is a separate subsequent adaptation from the approved source, not from B2.

## Frankenstein trial, 2026-09-14

Source: `shelley-frankenstein-en-orig`, Chapter V (chapter sequence 11),
28 blocks / 12,920 characters. Source C1 label and all original blocks unchanged.

Prompt v1, run `4d7cbbf4-b9ad-4697-8bf9-7faa6d55856e`, quality model
`gpt-5.6-terra`: estimated $0.056442. Four blocks kept exactly. Initial validation
rejected a false “kept” label on a changed speech attribution in `c11.p17`.
The saved response was recovered without another paid request; text was not
silently corrected to match the model's label.

Editorial inspection: easier syntax and retained Gothic imagery, but still
obstructive historical senses (“watching” for staying awake, “diligence” as a
vehicle). The change from Henry's firm hope to certainty in `c11.p20` strengthens
his belief. Changing “object” to “someone” in `c11.p25` softens Victor's
dehumanizing perspective. These are substantive reasons to refine the prompt,
not grounds for declaring B2 achieved from a generated label.

Prompt v2 explicitly addresses historical senses, same-period equivalents,
degrees of belief and the narrator's attitude, and forbids gratuitous changes
to simple speech attributions. This is an editorial iteration on real text,
not a claim of calibrated CEFR accuracy.

Prompt v2, run `500ffbdf-07e3-4a86-af2b-a36def636d70`, estimated $0.069128:
fixed the hope/certainty drift and “diligence” became “stagecoach”; preserved
the dehumanizing “object” and simple dialogue. However, it was too conservative
about difficult syntax and still retained “watching” in its historical sense.
Do not treat it as an approved B2 edition. Prompt v3 retains these fidelity
constraints but explicitly requires unpacking dense subordinate clauses, not
merely substituting a handful of words.

Prompt v3, run `fc0f975c-70a4-4537-ab9a-183431cad45a`, estimated $0.055728:
all 28 blocks present, four kept verbatim. The opening and nightmare now have
clearer sentence structure; “watching” becomes “awake”, “support the horror”
becomes “bear the horror”, and Henry's hope remains hope. Total estimated spend
for the three trials: **$0.181298**. The original source snapshot still matches.

Agent editorial assessment after reading all three outputs: v3 is the useful
direction for direct original→B2 adaptation. It preserves the main events,
nightmare, dialogue and Gothic images while making the action substantially
easier to follow. This is a draft for review, not human approval or a verified
CEFR rating. Specific remaining edits to discuss before a full-book run:

- `c11.p27`: “my first thought would not fly towards” became “turn towards”.
  The original image is accessible; keep it rather than flatten it.
- `c11.p23`: “as you promised yourself” became “you had hoped to spend”.
  This weakens the commitment; retain the stronger intention.
- `c11.p5`: “accidents of life” still risks being read as mishaps rather than
  chance events. Clarify the historical sense without changing the contrast.

The paid versions remain separate in the staff UI, including the earlier
imperfect drafts. No full-book generation or publication was launched.

Second review of v3, 2026-09-14 (independent read of all 28 blocks): the
direction is confirmed, but v3 also regressed on a point v2 had held.
`c11.p25` “an object on whom I dared not even think” became “the being of
whom”, softening Victor's dehumanizing reference. Also, `c11.p5` turned “now
that I had finished” into “now that I had succeeded” (an outcome the source does
not state) and “livid with the hue of death” into “deathly pale” (livid is
bluish-grey, not pale); `c11.p8` reads “showed … which showed” after
substitution, and “the sixth hour” could be “six o'clock”. Several change
reasons mislabel formal words as historical (“spectre”, “lifeless”). The
`c11.p2` import defect “I t was” was silently normalized in the adaptation;
the source record still needs its own correction.

Prompt v4 restructures the same rules under headed sections and adds the
specific guards these slips need: accessible phrases inside adapted blocks stay
verbatim (with “fly towards” as the example), dehumanizing words for the
creature are never softened, a firm intention is not a wish, an outcome is
never added, obsolete senses are always replaced rather than kept (with
“accidents” as the example), sensory words keep their exact meaning, and the
change reason must name the real barrier. Alongside v4 the service gained a
guard that refuses to run when a saved prompt version's text or schema differs
from the code (bump the version instead), a warning when an “adapted” block
differs only in punctuation, spacing or case, and word-level diff highlighting
on the review page so reviewers see exactly what changed in each paragraph.

Prompt v4, run `ef7bd349-9a3d-4d0a-953c-b21839dd9e59`, estimated $0.060184
(5,420 input / 4,112 output tokens, 313 reasoning): all 28 blocks present,
seven kept verbatim. Every targeted slip is fixed: `c11.p23`, `c11.p27` and
`c11.p14` are now kept exactly; `c11.p25` keeps “object” (“Could he refer to an
object…”); `c11.p5` reads “chance events”, keeps “now that I had finished” and
renders “livid” as “bluish-grey”; `c11.p8` replaces the obsolete “discovered”
with “revealed” and no longer repeats “showed”. Trade-offs: v4 is slightly more
conservative on syntax than v3 (the long final sentence of `c11.p2` stays
unsplit), “at the very moment of my getting down” in `c11.p10` is clumsy where
v3 had “I arrive”, “unbelieving” in `c11.p11` is odd where v3 had
“unconvinced”, and the `c11.p21` reason claims “bestowed existence” was replaced
when it was kept. Total estimated spend for four trials: **$0.241482**.

Assessment: v4 is the more faithful draft and the better base for a full-book
run; v3 is the more fluent one. The next prompt iteration, if any, should push
v4's syntax unpacking back toward v3 (specifically the `c11.p2` pattern of
splitting a “when, by…; it…, and…” sentence) without loosening the v4 fidelity
guards. Neither is human-approved or a verified B2 rating.

Existing import issues also visible in this source: `c11.p2` starts “I t” and
`c11.h3` is an illustration quotation tagged as a heading. Source cleanup is
separate from adaptation. The pilot does not modify those original records.
# Target-level gate and prompt review — 2026-09-15

**Later follow-up:** the feedback-corrected Chapter IV pilot has now been applied
to the draft with 13 audited block changes, followed by two audited wording
corrections. The original and other chapters remain untouched. The account below
records the earlier pilot-review state; see [current cross-product delivery and
content state](PRODUCT_READER_DELIVERY.md#local-content-update).

The existing full-book draft is **v4**, not v6/v7. No chapter text or published
edition was overwritten during this review. Its old judge result was 9 B2 / 21 C1.
The revised blind judge (chapter-analysis prompt v3, operational rubric v2)
returns **29 B2 / 1 C1**, with Chapter IV (sequence 10) still C1. The book's p75
therefore becomes B2, but the new adaptation gate still blocks it. This is a
change in the assessment method, not evidence that unchanged text improved.
The complete original-control run with the same revised judge returns **18 B2 /
12 C1, aggregate C1**. Its editorial C1 label and published text remain unchanged.

The previous rubric associated C1 with literary prose and implicit attitudes;
some evidence confused horror, cultural references and regional spelling with
language difficulty. The revision asks for representative, recurring linguistic
barriers, separates content flags from CEFR, and does not give the judge an
adaptation target. It remains an uncalibrated estimate. The same judge rates
original Chapter IV C1, v4 Chapter IV C1, and v5/v6 pilot Chapter IV B2. Original
and v4 Chapter V both rate B2; identical bands do not mean identical reading ease.

Generation v5 relaxes exact phrase preservation when it obstructs sentence-level
readability. A full Chapter IV pilot reached B2 but agent review rejected its
"every soul and sensation" and weakened "emaciated" → "thin". v6 added idiom,
quantifier and intensity checks. Both Chapter IV and Chapter X v6 pilots reached
B2, but review still found intensity loss and a scope reversal: "which I only do
not fear" became "which alone do not frighten me". These pilots are **not
approved**, despite passing the difficulty judge. Their findings remain visible
on their saved pilot pages. v7 adds explicit semantic-scope, unspecified-sensation
and historical-unit constraints. Do not regenerate the full book just because
a pilot receives the requested band.

## What is live

- Edition page shows requested target separately from editorial and computed
  levels, above/below-target chapters, every window estimate and its cited evidence.
- Review completion and publication both recheck current difficulty. Missing,
  stale or partial assessment blocks completion. Any above-target window blocks,
  including excluded front/back matter; p75 and editorial overrides cannot hide it.
- Below-target chapters are reported, not rejected: target is an upper reading
  demand, not a requirement to make accessible text harder.
- Standalone pilot assessment is bounded, blind, cached and recorded in AIRun.
  The saved pilot displays judge model/version, cost, evidence and review findings.
  It does not create an edition or publish anything.
- The staff pilot form accepts bounded editorial corrections. They are stored
  in the run and full request, included in its idempotency hash, and shown beside
  the comparison. Regeneration uses the original, not a previous generated text.
- Imported adaptations without explicit generation-target provenance are not
  covered by this gate; adding a persistent target field/editorial workflow for
  those is still a separate task.

Explicit paid worker operation for an already completed standalone pilot:

```python
from almonium_book_processor.catalog.pilot_difficulty import assess_pilot
assessment = assess_pilot(pilot_id)
```

This is not called by a reader GET or CI. Failed/interrupted pilot assessments
require ledger inspection before retry, rather than silently charging again.

Prompt changes use clear priorities and explicit success constraints, following
[OpenAI's prompting guidance](https://developers.openai.com/api/docs/guides/reasoning-best-practices#how-to-prompt-reasoning-models-effectively).
That guidance does not validate our CEFR classifications or literary fidelity.

## Latest testable candidates

Both v7 + recorded feedback candidates receive B2 from the blind v3 judge:

| Chapter | Pilot ID | Generation + assessment |
|---|---|---|
| IV (sequence 10) | `da64bf26-f698-4c8d-b1ce-af83934eda8c` | $0.056235 |
| X (sequence 16) | `c85ecc02-7b42-453d-ba0e-f999b765ae72` | $0.058204 |

Staff routes are `/editions/da3a845f-572c-4ed3-acf3-3172bbc972f9/adaptation-pilot/{pilot-id}/`.
Agent review compared both complete chapters against the source. The targeted
scope, intensity and sensory-interpretation errors are fixed. Chapter X preserves
and explicitly flags `its dependent mountains` rather than inventing a modern
interpretation. Chapter IV still has two editorial concerns: `I alone should be
kept to discover` is awkward, and `hopes` weakens `aspires`. These are **readable
pilot candidates, not publication approvals**. Generic v7 alone did not solve
every fidelity issue; keep the generation → blind difficulty → fidelity review →
bounded correction loop. No existing book text was replaced.

Next useful work:

1. Resolve Chapter IV's remaining wording concerns and apply its accepted result
   through an audited, revision-aware chapter replacement; re-run downstream
   sentence, lexical and difficulty artifacts. Do not regenerate 29 chapters
   merely because they belonged to the earlier draft.
2. Make bounded fidelity checking/correction a worker workflow, retaining explicit
   uncertainty rather than promising that a B2 label proves semantic accuracy.
3. Deliver offline N:M sentence alignment to the existing clickable preview, then
   verify the approved edition's backend/frontend publication round-trip.

Operational note: a worker replacement interrupted one original-control judge
request. Its AIRun remains failed with unknown provider charge (not zero); completed
windows were reused when the control resumed. Subsequent restart used a long
grace period to let active work finish. No CI request was paid.

## B1 chapter pilots — 2026-09-17

The staff chapter-pilot form now offers B1 alongside B2. B1 uses its own prompt
v1 (`literary-b1-adaptation-pilot`) and processor (`b1-chapter-pilot-v1`). The
existing B2 v7 prompt and full-book generation identities remain unchanged.
B1 inherits the fidelity and protected-block rules, with explicit guidance for
common vocabulary, natural word order, shallow clause structure and connected
prose. Necessary qualifications, uncertainty, imagery and adult tone must survive;
remaining barriers that cannot be simplified faithfully belong in review notes.

Generate B1 and B2 siblings from the same approved source. Start with the reviewed
Frankenstein IV and X passages to compare reflective syntax, narrative action and
known fidelity traps. Review the source/B1 comparison, then use the existing blind
pilot assessment; a requested B1 label does not establish achieved difficulty.
The assessment is still an estimate and does not replace fidelity review.

This change enables standalone B1 pilots only. Full-book generation and applying
pilots to draft editions remain B2-only. No paid generation or assessment was run
as part of this implementation; fake-provider tests verify workflow behavior,
not the model's B1 output quality.

## Agent-owned B1 delivery — 2026-09-17

The user authorized paid generation and assessment, with the agent responsible
for fidelity review and deciding when to generate the complete book. The earlier
standalone-only restriction is superseded: resumable full-book B1 generation,
level-preserving retries and applying assessed B1 chapter revisions are supported.
B1 and B2 retain separate identities and derive from the same source.

Initial B1 v1 samples (preface, IV and X) all received B2 from the existing blind
judge. Direct comparison found weakened intensity (`emaciated` → `thin`) and an
invented dependency in `its dependent mountains`. B1 v2's extra instructions
still left formal, nested prose. B1 v3 therefore uses a dedicated prompt with
explicit examples of sentence reconstruction, preserving the fidelity rules.
The B2 v7 prompt and blind judge remain unchanged.

The language target follows the Council of Europe's
[reading-for-leisure descriptors](https://rm.coe.int/cefr-webinar-series-2021-4-handouts/1680a54fd5):
straightforward stories using everyday vocabulary, with dictionary support.
This guides editorial decisions; an automated estimate is not CEFR certification.
Generation must preserve the book's arguments and atmosphere, not summarize them
to make its subject easier.

## Decision after judge controls — 18 September 2026

**Do not generate or publish a full B1 Frankenstein with the current workflow.**
B2 remains the supported reading floor for this book under the tested fidelity
rules and Terra ceiling. This is an operational decision, not proof that a
skilled human could never write a faithful B1 adaptation. No premium model was
called. No local, staging or production B1 edition was created.

The unchanged blind Luna judge (prompt v3, rubric v2) was run on eight controls.
Source labels and intended levels were withheld from its input:

| Control | Result |
| --- | --- |
| Original Preface | C1 |
| Original IV | B2 |
| Original X | C1 |
| Published B2 Preface / IV / X | B2 / B2 / B2 |
| Agent-authored everyday journey | B1 |
| Agent-authored reflective disagreement | B1 |

The authored controls are intended B1-style prose, **not externally certified
CEFR benchmarks**. They demonstrate that this judge can distinguish simple
connected prose, including adult reflection, from our adaptations. They do not
establish a calibrated classifier. The original book's C1 editorial label is
not a ground truth for every chapter: IV returned B2 here, unlike an earlier
C1 result. That variability argues against repeated scoring until a label passes.
The judge was not loosened to approve an adaptation.

[Inputs](evidence/b1-20260918/control-stories.json),
[complete assessments and AIRun IDs](evidence/b1-20260918/judge-controls-v3.json).
The ledger estimate was $0.016264 using the historical mean, with $0.08 reserved
conservatively before calling. Actual cost was **$0.012511**. The session began
with $6.671163 recorded project spend; the new session limit is $10 incremental.

Current prompt v5 already ran on Terra at **high** reasoning on exactly the
same three original passages. Reusing those saved runs avoids paying again for
identical inputs. All three remain B2 under the blind judge:

| Passage | Generation | Fidelity audit | Findings |
| --- | ---: | ---: | --- |
| Preface | $0.022042 | $0.010008 | No flagged fidelity issues; still B2 |
| IV | $0.049697 | $0.062828 | Two minor sense/image shifts; still B2 |
| X | $0.067005 | $0.069656 | Five minor shifts in resolve, imagery, force or clarity; still B2 |

[Generation history](evidence/b1-20260918/generation-history.json) and
[v5 audit evidence](evidence/b1-20260918/v5-fidelity.json) retain exact run IDs.
There were 15 generation attempts across five prompt versions, **13 completed
and assessed B2**, plus two v3 requests interrupted by a container replacement.
Their provider outcomes and costs were not recorded; they are not successes or
known-free calls. This corrects the shorthand “five versions × three assessed”.

My review agrees that “unprotected” weakens the warning about being unwary,
“vines produced wine” damages the agricultural image, and “ask” weakens “demand”.
The audit's suggestion to drop “smallest sound” from the avalanche passage
would itself lose a claim: its awkwardness partly reflects the original. Audit
suggestions require judgment; a clean audit is not a fidelity certificate.
Even accepting every minor trade-off would not solve the failed B1 difficulty gate.

An honest alternative is the already published B2 text with original-derived
Ukrainian support. A future more freely rewritten or abridged B1 must be a
separately described editorial product with explicit approved losses; it must
not inherit a claim of full fidelity. A2 has not been tested and is not licensed
by these results. “At most two CEFR rungs” is a planning heuristic, not evidence
that every C1 book can reach B1 while retaining every claim and image.

B1 becomes a new experiment only with a materially different generation strategy
(e.g. planned restructuring with claim-by-claim reconciliation), a genuinely
matched B1 source, or explicitly disclosed abridgement and fidelity trade-offs.
The affordable product now is honestly labelled **B2 with reader aids**. Neither
a higher label tolerance nor another synonym-only prompt revision supplies the
missing evidence. These routes need fresh blind controls and fidelity gates.

## The floor as data — 2026-09-18

Decision 13 is now machinery rather than a note. Nothing below sets a level by
hand; every state on the card is read from runs in the ledger.

**Fidelity audit** (`catalog/fidelity_audit.py`, processor
`fidelity-audit-v1`). The literary-editor prompt from the evidence scripts is
the saved `literary-fidelity-editor` v1 row, byte for byte. A pilot audit
reads the sample beside the snapshot it was generated from; an edition audit
reads every chapter of an adaptation beside its source edition, one paid
request per chapter (split by block only past 160 KB), each cached by input
hash so a text fix re-reads one chapter. Material findings become
`adaptation_fidelity_finding` review items on the block; minor and uncertain
ones get the same treatment. Every finding is a text-quality finding on its
block with the quoted span located: **apply** writes the suggested wording in
as an audited block revision, **dismiss** records that the adapted wording
keeps the author's meaning. Both exist per finding and in bulk, behind a
confirmation; a finding whose quote cannot be placed as one span is
dismiss-only and asks for a hand edit. Only open material findings hold the
gate. Applying queues the sentence, vocabulary and difficulty refresh for the
changed chapters, and the next audit re-reads only those chapters, because
windows are cached by model, effort, prompt and text. A newer audit
supersedes the older run's open findings. The audit tier is
`OPENAI_FIDELITY_TIER` (`quality` = Terra by default, `draft` = Luna at about
a tenth of the price); a comparison run under another tier keeps its review
in the ledger without writing findings.

**Every staff pilot is judged and audited** as soon as it generates: the
worker task runs the blind difficulty judge and the fidelity audit after the
pilot, so the pilot page always shows both. Full-book chunks are not judged
individually; the edition's chapter analysis and edition audit cover them.

**Floor probes** (`catalog/adaptation_floor.py`, processor `floor-probe-v1`).
A probe at a level generates pilots on the first, middle and last substantive
chapters that fit the pilot limits, judges each blind and audits each. It
passes when every chapter's highest judged window is at or below the target
and no material finding was raised; otherwise it fails and its reasons are
kept. Its identity is the generation prompt and model, the judge prompt and
model, the audit prompt and model, and the sampled text, so the same
configuration is never rolled twice: a rung is retried only under a new
version. Probes go one rung at a time below the original's level: B1 cannot
be probed until B2 has a passed probe or a reached edition.

**`adapts_to`** is recomputed by `refresh_adaptation_floor` whenever a gate
changes (difficulty projections, an audit finishing, a finding resolved, a
review completed, a purge). It is the lowest level among the work's
adaptation editions that pass both gates for their current text; the
evidence records the edition, its chapter-analysis run and its audit run, and
for probed levels the probe and pilot ids. A promoted work keeps the floor it
arrived with, because the ledger that justifies it stays in the environment
that paid for it; the bundle schema is now 4.

**What the operator sees.** The original edition's "Level adaptation" panel
is a ladder: the original's level, then one rung per level below. Each rung
shows its state (untried, probing, probe passed, probe failed, edition
generated, reached) with the runs behind it, and exactly one action where one
applies: "Probe B2", then "Generate full B2 edition" once the probe passes,
then "Probe B1" once B2 is reached. A failed probe reads "floor" and leaves no
button until a new prompt or model version exists. An adaptation's page gains
a "Fidelity audit" panel with the run, counts and the paid button.

**What ships.** The publication payload carries `adaptsTo` and
`reachedLevels` alongside `cefrLevel`; the product API ignores unknown fields
until it stores them, which is the next cross-repository step.

Frankenstein, 2026-09-18: the published B2 edition was audited on Terra
(run `f06a3841`, 815 blocks, $1.32): 7 material, 36 minor, 2 uncertain
findings, 44 of 45 with their quotes placed in the text. Five of the material
ones are plain errors (leagues became miles; "fear not but that" reversed;
"hasten my delay"; "eventual" weakened to "possible"; "resignation" became
"acceptance"). They are open findings on the edition's page, to apply or
dismiss; `adapts_to = B2` follows once no material one is open. B1 is a
failed rung, backfilled from the three v5 pilots (`backfill_floor_probe`),
so the ladder reads B2 generated, B1 floor.

## Final B1 follow-up — 18 September, afternoon

| Strategy | Preface | IV | X | Fidelity against original | Added cost |
| --- | --- | --- | --- | --- | ---: |
| v1–v5, original → requested B1 | B2 | B2 | B2 | v5: seven minor findings across three passages | See ledger above |
| v5, published B2 → requested B1 | B2 | B2 | B2 | One uncertain, five minor, one material | $0.269100 |

The [completed two-stage experiment](evidence/b1-20260918/two-stage-b2-to-b1.json)
uses pilots `3f0d2971`, `d7f333de`, `2df4b589`; it was **not rerun**.
The material finding is “more necessary beings” becoming “more necessary slaves”.
The creature's direct accusation becoming passive is a separate **minor** finding.
Two-stage generation did not lower difficulty and introduced fidelity problems.

The stored chapter-analysis-v3 distribution rules out an aggregation artefact:
published B2 has **32/32 B2 windows, 100% of analyzed words**, confidence
0.94–0.98. Original English has **13/32 C1 windows (47% of words)** and
19/32 B2 windows. These operational estimates support moving the difficult
windows down to B2, not a hidden B1 core concealed by a maximum-level summary.
Reproduce from the latest successful chapter-analysis run for each edition:

```python
from collections import Counter
from almonium_book_processor.catalog.models import Edition, AIRun
for slug in ("shelley-frankenstein-en-orig", "shelley-frankenstein-en-orig-b2"):
    edition = Edition.objects.get(slug=slug)
    run = edition.pipeline_runs.filter(
        stage="chapter_analysis", status="succeeded",
        summary__spec__prompt_version=3,
    ).order_by("-created_at").first()
    counts, words, confidence = Counter(), Counter(), []
    for ai in AIRun.objects.filter(pipeline_run=run, status="succeeded"):
        result = ai.response_payload["analysis"]
        level = result["cefr_estimate"]
        counts[level] += 1
        words[level] += sum(len(b["text"].split())
                            for b in ai.request_payload["window"]["blocks"])
        confidence.append(result["confidence"])
    print(slug, run.id, counts, words, min(confidence), max(confidence))
```

**With fidelity as a constraint, B2 is the observed floor for this book and
these generation strategies.** B1 would be a disclosed abridged retelling, a
different product requiring the user's decision. Decision 13 forbids forced
abridgement: no level is promised in advance. `adapts_to` is evidence-derived;
the product's reached-level gate also requires the B2 edition's own fidelity
audit, independently of the B1 pilot verdict. A matched B1 source or materially
different strategy could reopen research, with new evidence rather than relabelling.
