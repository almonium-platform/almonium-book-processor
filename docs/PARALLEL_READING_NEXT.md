# Parallel reading assessment — 18 September 2026

**Keep the original-derived Ukrainian edition as an honestly labelled companion
for B2 English.** It is useful to a fluent Ukrainian reader learning English,
but it is not a B2 Ukrainian translation or a word-for-word key. Do not offer it
as simplified Ukrainian for a learner whose Ukrainian is also intermediate.
No new translation or alignment calls were made for this assessment. No B1 edition exists.

## Current evidence and denominators

The handoff's 815 blocks / 2,190 confident groups / 49 paragraph-only blocks
belong to the historical MiniLM v2 run `ba22bf2d-fc0a-499a-887d-44f999022148`.
The already-saved current LaBSE v5 B2–UK run is
`9ee73dec-31a3-49d6-a6cf-b31e5795458d`: **815 blocks, 3,904 confident groups,
19 paragraph-only blocks (2.33%)**. Original–UK uses
`33e3139c-4f52-418b-a3fc-504898536e81`: 4,489 groups, nine paragraph-only blocks.
These improvements predate this assessment; they are not tonight's generation.

All 815 blocks retain inherited paragraph partners. Confident *display-unit*
coverage is 4,137/4,942 (83.7%) for B2 and 4,576/4,811 (95.1%) for original.
Those units include semicolon clauses: **they are not canonical sentence counts**.
Mapping accepted display spans back into the stored NLP sentence offsets gives:

| English edition | Canonical sentences | Any confident UK counterpart | Fully covered | Partly covered | No confident sentence counterpart |
| --- | ---: | ---: | ---: | ---: | ---: |
| B2 | 4,085 | 3,375 (82.62%) | 3,362 (82.30%) | 13 | 710 |
| Original | 3,454 | 3,272 (94.73%) | 3,269 (94.64%) | 3 | 182 |

Full coverage means every display span inside the English sentence participates
in an accepted two-sided group. “No counterpart” means no **confident sentence
link**, not omitted Ukrainian text: the paragraph remains available. This is
alignment coverage, not a measured percentage of semantic fidelity.

After collapsing clause links into connected canonical-sentence groups, B2 has
3,044 accepted components: 2,732 one-to-one (89.75%), 305 many-English-to-one-UK
(10.02%), three one-English-to-many-UK (0.10%), four many-to-many (0.13%).
These describe mapping cardinality, not proof of which editor split a sentence.
The original has 3,260 components, 3,245 one-to-one (99.54%).
Eighteen of B2's 19 paragraph-only blocks are paragraphs; one is a heading.
Eight fallback blocks are also fallbacks in original–UK; eleven are B2-only.

[Canonical counts and gaps](evidence/parallel-20260918/canonical-metrics.json),
[display-unit counts](evidence/parallel-20260918/display-unit-metrics.json), and
[source revisions and run identities](evidence/parallel-20260918/manifest.json)
preserve the measurement. Reproduction: obtain `inherited_payload(english, uk)`,
join each displayed span to its containing `ContentBlock.sentences` span, count
only groups with `certain` and both sides nonempty, and take unique parent
sentences. Collapse shared parent links before counting split/merge components.
Never divide clause counts by the canonical-sentence denominator.

## Per-chapter breaks

Percentages in the split/merge columns use that chapter's accepted canonical
components. Paragraph fallback is a count over all blocks in the chapter.
Sequence 7 is Chapter I; sequences 1–6 include the introductions and letters.

| Sequence / title | Fully linked English sentences | Partial sentences | Many EN → one UK | One EN → many UK | Many → many | Paragraph-only blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1: INTRODUCTION. | 91/113 (80.5%) | 1 | 6 (7.1%) | 0 (0.0%) | 0 (0.0%) | 0/19 |
| 2: PREFACE. | 20/25 (80.0%) | 0 | 2 (11.1%) | 0 (0.0%) | 0 (0.0%) | 0/7 |
| 3: LETTER I. | 53/56 (94.6%) | 0 | 2 (3.9%) | 0 (0.0%) | 0 (0.0%) | 0/14 |
| 4: LETTER II. | 53/72 (73.6%) | 1 | 7 (15.2%) | 0 (0.0%) | 0 (0.0%) | 0/12 |
| 5: LETTER III. | 19/25 (76.0%) | 0 | 1 (5.9%) | 0 (0.0%) | 0 (0.0%) | 0/9 |
| 6: LETTER IV. | 104/141 (73.8%) | 0 | 5 (5.1%) | 0 (0.0%) | 0 (0.0%) | 0/40 |
| 7: CHAPTER I. | 69/91 (75.8%) | 0 | 4 (6.2%) | 0 (0.0%) | 0 (0.0%) | 0/12 |
| 8: CHAPTER II. | 91/102 (89.2%) | 0 | 11 (13.9%) | 0 (0.0%) | 0 (0.0%) | 0/17 |
| 9: CHAPTER III. | 130/145 (89.7%) | 0 | 17 (15.2%) | 0 (0.0%) | 1 (0.9%) | 1/23 |
| 10: CHAPTER IV. | 85/113 (75.2%) | 1 | 12 (16.9%) | 0 (0.0%) | 0 (0.0%) | 0/15 |
| 11: CHAPTER V. | 95/137 (69.3%) | 2 | 16 (19.8%) | 1 (1.2%) | 0 (0.0%) | 2/28 |
| 12: CHAPTER VI. | 121/143 (84.6%) | 0 | 9 (8.0%) | 0 (0.0%) | 0 (0.0%) | 1/24 |
| 13: CHAPTER VII. | 196/212 (92.5%) | 0 | 4 (2.1%) | 1 (0.5%) | 0 (0.0%) | 0/52 |
| 14: CHAPTER VIII. | 151/183 (82.5%) | 1 | 10 (7.2%) | 1 (0.7%) | 3 (2.2%) | 0/34 |
| 15: CHAPTER IX. | 95/103 (92.2%) | 0 | 5 (5.6%) | 0 (0.0%) | 0 (0.0%) | 0/17 |
| 16: CHAPTER X. | 117/141 (83.0%) | 0 | 6 (5.5%) | 0 (0.0%) | 0 (0.0%) | 0/17 |
| 17: CHAPTER XI. | 115/139 (82.7%) | 1 | 15 (14.9%) | 0 (0.0%) | 0 (0.0%) | 0/20 |
| 18: CHAPTER XII. | 89/101 (88.1%) | 0 | 6 (7.2%) | 0 (0.0%) | 0 (0.0%) | 0/20 |
| 19: CHAPTER XIII. | 90/101 (89.1%) | 1 | 13 (16.9%) | 0 (0.0%) | 0 (0.0%) | 2/23 |
| 20: CHAPTER XIV. | 68/87 (78.2%) | 0 | 13 (23.6%) | 0 (0.0%) | 0 (0.0%) | 0/21 |
| 21: CHAPTER XV. | 143/195 (73.3%) | 0 | 16 (12.8%) | 0 (0.0%) | 0 (0.0%) | 2/39 |
| 22: CHAPTER XVI. | 125/172 (72.7%) | 3 | 8 (6.7%) | 0 (0.0%) | 0 (0.0%) | 3/38 |
| 23: CHAPTER XVII. | 81/92 (88.0%) | 0 | 2 (2.5%) | 0 (0.0%) | 0 (0.0%) | 1/22 |
| 24: CHAPTER XVIII. | 113/134 (84.3%) | 0 | 5 (4.7%) | 0 (0.0%) | 0 (0.0%) | 0/25 |
| 25: CHAPTER XIX. | 106/118 (89.8%) | 1 | 8 (8.1%) | 0 (0.0%) | 0 (0.0%) | 0/24 |
| 26: CHAPTER XX. | 142/182 (78.0%) | 0 | 17 (13.7%) | 0 (0.0%) | 0 (0.0%) | 0/38 |
| 27: CHAPTER XXI. | 150/194 (77.3%) | 0 | 24 (19.7%) | 0 (0.0%) | 0 (0.0%) | 2/50 |
| 28: CHAPTER XXII. | 146/164 (89.0%) | 1 | 8 (5.8%) | 0 (0.0%) | 0 (0.0%) | 2/42 |
| 29: CHAPTER XXIII. | 107/120 (89.2%) | 0 | 9 (9.2%) | 0 (0.0%) | 0 (0.0%) | 1/31 |
| 30: CHAPTER XXIV. | 397/484 (82.0%) | 0 | 44 (12.6%) | 0 (0.0%) | 0 (0.0%) | 2/82 |

## Read-through judgement

I read the complete B2 and Ukrainian Preface, Chapter V and Chapter X side by
side (52 blocks; 5,115 English words), including the dialogue and long paragraphs.
My verdict: **usable paragraph-level support, uneven sentence-level support**.
Events, reasons and viewpoint remain easy to locate, but long Ukrainian periods
frequently span several simplified English sentences. A learner should read the
whole paired paragraph when a highlight disappears, not infer missing meaning.

- Preface `c2.p3`: B2 separates the literary precedents and the novelist's freedom;
  Ukrainian keeps them in one long argument. The correspondence is understandable,
  but the 3-to-2 display group is correctly left uncertain. Abstract phrasing is
  still demanding in both languages; this is not a beginner-friendly section.
- Chapter V `c11.p2` and `c11.p5`: the animation scene, nightmare and escape stay in
  the same order. Splitting the clock/rain/candle sequence and rearranging sentence
  boundaries weakens highlighting. The nightmare paragraph contains several
  uncertain groups despite a clear narrative correspondence. `c11.p20` retains
  Henry's **hope**, rather than turning recovery into certainty.
- Chapter X `c16.p2`: the glacier imagery and consolation survive, but the Ukrainian
  landscape sentence is much longer than the English. `c16.p12` maps the creature's
  appeal coherently using grouped spans; `c16.p16` preserves “I demand” / “я вимагаю”,
  and `c16.p17` retains suspicion rather than asserting that the creature is guilty.
  `c16.p5` uses approximately three miles in B2 against the historical Ukrainian
  “льє”: useful to understand the scene, unsuitable as a literal vocabulary key.

The audit also exposes existing text roughness, independently of alignment:
`c11.p11` inconsistently spells Clerval as “Керваль” once; B2 `c11.p21` has
“on whom I had given existence”; `c16.p4` retains the awkward “necessary slaves”.
These are review candidates, not edits or approvals. The full B2 fidelity audit
separately flags material problems; good alignment does not clear that gate.
Breaks cluster in long descriptive and reflective paragraphs, with many missed
links in the creation scene and later long chapters. The table gives the local
rates rather than hiding them inside the book-wide average.

## Recommendation and cost of another companion

Keep C1-UK with the existing “translation of the original, not this adaptation”
identity/label, preserve paragraph fallback, and make no matched-level claim.
The C1 label is inherited from the source edition; it is not proof that every
Ukrainian chapter independently judges C1. This route costs **$0** in new translation.

If a level-matched Ukrainian companion becomes a separate product decision,
the cheapest plausible route is a draft-model Ukrainian simplification of the
existing UK text, preserving block IDs, followed by independent difficulty and
fidelity gates. Do not assume English's B2 floor applies to Ukrainian. Test a
few representative chapters first; do not translate B1/B2 editions now.

The existing whole-book Terra translation cost **$2.062207**. Repricing its same
recorded token mix at the configured Luna rates (one tenth of Terra's rates)
gives **$0.206221 for generation only**, an indicative lower-cost workload proxy,
not a quote for a Ukrainian adaptation. The completed 30-chapter Terra B2
fidelity audit cost **$1.323934**; current Luna chapter analysis is about $0.10
per 48 Ukrainian windows. Thus roughly **$1.65 plus retries and editorial time**
is a defensible planning baseline for a cheaper matched-level attempt, with no
promise it passes. Generation-only savings do not remove the review cost.

The next useful investment is reviewing the existing fidelity findings and
correcting concrete language defects, before financing another full companion.
