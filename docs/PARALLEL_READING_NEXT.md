# Parallel reading: review and next visible deliveries

Reviewed 2026-09-14 against the local Frankenstein editions and current code.
This is a review and delivery plan, not a publication approval.

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

### R1 — Make the existing pairing reach the product

This is the focused first slice of P0-2/P2-3, not a new platform project.

- Serve inherited `align_group` pairs in the public parallel endpoint alongside
  the reviewed inferred-alignment path. Today it only reads `BlockAlignment`;
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
