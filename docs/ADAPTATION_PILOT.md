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
