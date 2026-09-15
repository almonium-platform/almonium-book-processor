# Parallel reading: review and next visible deliveries

Reviewed 2026-09-14 against the local Frankenstein editions and current code.
This is a review and delivery plan, not a publication approval.

## Implementation update — 2026-09-15

Follow [the cross-product delivery sequence](PRODUCT_READER_DELIVERY.md) for the
next sessions, including the unfinished Expo contract/UI work. Reviewed pilot
chapters can now replace draft chapters with revision history and re-analysis;
this does not approve or publish them automatically.

### Priority correction — offline alignment and achieved adaptation level

The user explicitly reaffirmed offline/free sentence alignment. The paid preview
below is historical proof of the interaction, **not the default implementation
strategy**. No full-book paid sentence alignment was run. The unfinished paid
full-book expansion was removed before shipping; no source or generated text was
deleted. Exact identical sentence spans and one-sentence inherited paragraph
pairs now require no provider call. General N:M semantic alignment still needs an
offline worker implementation; sentence splitting alone does not establish a
correspondence. Keep paragraph fallback when uncertain. Phrase alignment comes
after sentence correspondence, not before it. Paid escalation must be explicit.

Current priority: an acceptable adaptation, not broader paid alignment. See
[the prompt/judge review](ADAPTATION_PILOT.md#target-level-gate-and-prompt-review--2026-09-15).
Then deliver offline sentence coverage in the existing clickable reader, followed
by a deliberate publication round-trip and chapter metadata in the product.

The first R1/R2 slice is implemented across processor, backend and Angular:
complete inherited-group public pairs, an explicit companion-edition endpoint,
sibling/level/type discovery, same-language panes, and clickable many-to-many
sentence highlights. Generated editions now pass the alignment publication gate
by validating complete inherited groups; publication still requires review,
metadata, editorial level and current sentence splitting. Adaptations no longer
settle translation orders in the backend.

Paid previews ran for `c11.p2`, `c11.p13`, `c11.p20` in adaptation → original and
adaptation → Ukrainian. Prompt v1 mishandled the greeting's overlapping boundaries;
v2 correctly produces a 2:2 group. The awakening maps 3:1 and the illness passage
contains two 2:1 groups. Twelve requests across both prompt versions cost an
estimated **$0.020948**. No book text or publication status was changed.

Staff preview (chapter 11; login required):
`/editions/f0617488-6553-4131-9a13-2e470a62ffa9/sentence-preview/5a0a2c21-0350-4500-aaae-98a634fccafe/?chapter=11`.
Replace the secondary ID with `da3a845f-572c-4ed3-acf3-3172bbc972f9` for the original.
The normal staff reader also links to the preview. Missing sentence artifacts
remain plain paragraph pairs. Inverting a cached pair is free; composing through
a third edition is not used.

Explicit worker trigger (bounded to one chapter, optionally selected blocks):

```bash
docker compose exec -T web python manage.py preview_sentence_alignment shelley-frankenstein-en-orig-b2 shelley-frankenstein-uk-parallel 11 --blocks c11.p2 c11.p13 c11.p20
```

Results are keyed by both block identities/texts/segmentations/groups/languages,
processor/prompt version and model. Retries reuse unchanged results; concurrent
claims do not duplicate paid work. Interrupted submitted runs require operator
recovery rather than silently billing again. AI runs retain usage/failures; no
paid calls occur in CI or reader GETs. Structured output follows the
[official OpenAI schema contract](https://developers.openai.com/api/docs/guides/structured-outputs),
with local index coverage validation; schema validity is not semantic proof.

**Next iteration remains backend/frontend-focused:** deliberate end-to-end
publication testing, typed chapter metadata/CEFR/vocabulary, pair-eligibility
discovery and provenance, then broader sentence/clause coverage. No manual book
rewrite is implied. See the neighboring backend's `docs/PROCESSOR_READER_CONTRACT.md`
and frontend's `docs/PROCESSOR_READER.md` for contracts and verification limitations.

## Reuse the original's translation

Yes: a faithful, unabridged adaptation can use a translation made from its
original as a meaning companion. Do not generate a translation for every level
by default. Label the panes honestly: **Simplified English (B2 target)** and
**Ukrainian translation of the original**. The latter is not a direct translation
of the simplified wording, and need not itself be B2 when it supports a fluent
language. Keep the original separately available.

Eligibility needs a compatible canonical source revision, preserved group
identity and actual coverage, not just the same Work or language. Independently
imported translations need reviewed inferred correspondence. Abridgements and
plot-changing adaptations are not automatically interchangeable companions.

## What the current text looks like

The staff reader pairs all 815 adaptation blocks with Ukrainian counterparts,
with no gaps. Six complete three-way passages were spot-checked across Chapter V,
Chapter X and the ending; this is not a full-book bilingual fidelity review.

| Passage | Observation | Reader consequence |
|---|---|---|
| `c11.p2`, creature awakening | The original and Ukrainian have three sentences; the adaptation has five. The original's long third sentence becomes three adaptation sentences. | Good paragraph correspondence; highlight needs 3:1 sentence mapping. |
| `c11.p13`, Clerval's greeting | Both adaptation and Ukrainian have three sentences, but the boundaries divide the reprimand and the description of Victor differently. | Equal sentence counts do **not** justify pairing by index. |
| `c11.p25`, Victor's fear | Original/adaptation say “object”; Ukrainian says “істоту” (being/creature). | Story meaning survives, but the dehumanizing nuance differs. |
| `c30.p79`, final speech | Adaptation makes “afford no light” explicit as “give no knowledge”; Ukrainian retains “не дали світла”. | Flag the literal rendering for editorial review; do not promise exact wording equivalence. |

The Chapter X argument retains the Adam/fallen-angel allusion and emotional
argument. Overall the sampled pairing works as reading support. The main
limitation is precision within paragraphs, plus occasional translation nuance,
not missing correspondence. The B2 target still has a computed C1 aggregate
(21 chapters C1, nine B2); that is an estimate, not proof that every flagged
chapter needs rewriting. Editorial level is unset.

## Next sessions, in delivery order

The tickets below record the original review scope; the implementation update
above distinguishes the delivered first slice from the remaining work.

### R1 — Make the existing pairing reach the product

This is the focused first slice of P0-2/P2-3, not a new platform project.

- Serve inherited `align_group` pairs in the public parallel endpoint alongside
  the reviewed inferred-alignment path. At initial review it only read `BlockAlignment`;
  there are zero such rows among these three editions, so publication alone
  would not make their public parallel reader work.
- Add explicit secondary-edition selection in the backend/clients. The current
  language-only selection cannot reliably select original English versus
  simplified English, or distinguish several editions in one target language.
  Preserve existing client compatibility.
- Expose accurate adaptation/translation labels and source lineage; do not
  equate every edition with a source ancestor to a translation.
- Validate and record current inherited-group alignment without inference.
  The existing Ukrainian edition is Ready but fails the current-alignment
  publication gate. Generated-edition text edits must also be able to refresh
  this validation; the generated path currently skips inferred alignment.
- Preserve publication/ownership/withdrawal boundaries. Reject incompatible
  roots, stale correspondence and unauthorized companions explicitly.

**Visible acceptance:** after deliberate editorial approval and publication,
select original ↔ adaptation and adaptation ↔ Ukrainian in the product reader;
all 815 blocks correspond, labels are truthful, and unavailable companions do
not leak. Cover Angular and Expo contracts. Do not publish merely to test code.

### R2 — Click a sentence and see its counterpart

Bring P5-1 forward as a small staff-reader preview on Chapter V, then ship the
same contract to the product. This preview can start independently of R1.

- Begin with many-to-many sentence groups inside existing paragraph groups.
  On click/tap, highlight the corresponding sentence or sentences in the other
  pane. Test original ↔ adaptation and adaptation ↔ Ukrainian.
- Generate bounded, pair-specific alignment artifacts with audited cost. Use
  exact sentence IDs or locally verified text spans; reject invented text or
  offsets. CI uses fake providers, never paid requests.
- Key results by both edition text revisions, segmentation version, direction,
  and aligner/model/prompt versions. Align only requested pairs/chapters.
  Original-mediated mappings can suggest candidates, not certify a different
  pair's clause correspondence.
- Retain paragraph fallback for uncertain/failed mappings and show unmapped
  text honestly. Sentence splitting may differ even when sentence counts match.
- Then refine selected groups into clause spans, allowing reordered and
  discontinuous spans. Store half-open Unicode code-point offsets and convert
  safely for JavaScript UTF-16 rendering. Existing word diff is not semantic
  alignment. Avoid permanently colouring every word.

**Visible acceptance:** click the awakening's three simplified sentences and
see the matching original/Ukrainian passage; the greeting must map by meaning
despite its equal sentence counts. Text edits invalidate the cached highlights.
Review actual output in the UI before expanding beyond the chapter.

### R3 — Improve content where reading actually suffers

Review remaining difficult passages and translation nuances in context. Revise
genuine barriers selectively; do not rewrite until an LLM happens to return B2.
Confirm an honest editorial level before publication. No prerequisite C1
modernization, B1 generation, calibration framework or all-language expansion.
Discover's book-sourced examples remain a useful subsequent feature (P3-2/3).

## Publication exists, but is not yet end-to-end ready for these pairs

The staff flow is: resolve actionable checks, confirm metadata and editorial
level, complete review to Ready, then **Publish to Almonium**. A worker performs
the authenticated hand-off; only success marks the edition Published. Current
sentence splitting and source alignment are required.

Local state at review: original Published; adaptation Needs review with no
editorial level; Ukrainian Ready but blocked on current source alignment. R1
addresses the additional public-reader integration gaps. No editions were
published or changed during this review.

Current staff preview:
`/editions/f0617488-6553-4131-9a13-2e470a62ffa9/reader/?parallel=5a0a2c21-0350-4500-aaae-98a634fccafe&chapter=11`.
