# Sentence and clause alignment

Updated 2026-11-18. How an edition's paragraphs are matched to a companion's at sentence
and clause level, what each version changed, and what the pilot across language pairs
measured. Everything here is local: a multilingual embedding model on the worker's CPU,
no paid API, no plan allowance.

## Where it sits

1. **Paragraphs** are exact by construction. A translation or an adaptation inherits its
   source's canonical block groups (`align_group`), so paragraph *i* of the German is
   paragraph *i* of the English. Nothing is inferred.
2. **Sentences and clauses** inside each paragraph pair are matched by the offline job
   (`catalog/offline_sentence_alignment.py`, `processing/sentence_correspondence.py`).
   One run covers one edition pair; its result is one `sentence_alignment` artifact per
   paragraph pair, keyed by the pair's text hash and the processor version, so an
   unchanged paragraph is never embedded twice and a correction re-runs only what it
   touched.
3. Sub-clause (phrase or word) correspondence is not attempted.

The job is **started by staff**, from the alignment page ("Align all chapters"), and
re-queued automatically only for pairs that were aligned before when a correction
retires their artifacts. New productions do not start it; see "Open" below.

A killed run (worker restart) is closed by the janitor after two hours of silence, like
the other one-process jobs, and starting it again resumes: every finished paragraph
comes back from its artifact.

## How v9 matches

1. spaCy sentence spans on both sides; LaBSE embeds the sentences; a monotonic dynamic
   programme over cosine similarity proposes 1:1, 1:2, 2:1, 2:2, 1:3 and 3:1 groups with a
   small length prior. A group is confirmed at similarity ≥ 0.82, or ≥ 0.75 when it beats
   every crossing alternative by 0.10. Gaps get positional groups, unconfirmed.
2. Every sentence is cut into clause chunks at `;` (two words a side suffice) and at
   `,` `:` `—` `–` `--` (four words a side), never rewriting text or offsets.
3. Confirmed sentence groups are refined one by one. **Consecutive unconfirmed groups are
   refined together as one region**, because an unconfirmed group usually means the two
   languages put a sentence boundary in different places, and a chunk must be free to
   find its partner across it.
4. Inside a group or region, the same dynamic programme pairs chunks. A chunk pair stands
   when its similarity is ≥ 0.6 **and** it beats every crossing pairing in the region by
   ≥ 0.2; the weakest pair otherwise merges with the neighbour it fits best, and this
   repeats until every pair stands or one group is left (then the sentence groups are
   kept as they were).
5. A chunk pair is confirmed when its sentence group was, or when it is small (≤ 3 chunks
   a side) and has similarity ≥ 0.7. A large pair left over in an unconfirmed region is a
   remainder, not a match, and stays unconfirmed.

The thresholds are in `sentence_correspondence.py` next to the code that uses them.

### German word order

German commas are obligatory before subordinate clauses, so a comma clause keeps its
verb-final verb: "Als die Droschke vor der angegebenen Adresse hielt," pairs with "As the
cab drew up before the address indicated,". What clause chunks cannot do is hold a
separable verb whose prefix lands in a later clause: in "Sogleich **laden** zwei Burschen …
in Goldstoff gekleidet …, sie **ein**, an der Tafel … Platz zu nehmen" the stem and the
prefix are two chunks apart. The chunks still pair correctly by meaning; no chunk holds
the whole verb. Finer than this needs word alignment, which is out of scope.

## Versions

| Version | Date | Change |
| --- | --- | --- |
| v1–v2 | 2026-09-15/16 | Whole-book offline sentence matching (MiniLM), staff preview. |
| v3 | 2026-09-16 | Long sentences chunked under the encoder window; distinct reciprocal matches accepted at 0.75 ([ALIGNMENT_FIX_20260916.md](ALIGNMENT_FIX_20260916.md)). |
| v4 | 2026-09-16 | LaBSE offered beside MiniLM (not committed alone). |
| v5 | 2026-09-17 | Semicolon clauses inside confirmed groups ([FRANKENSTEIN_TEXT_AND_CLAUSES.md](FRANKENSTEIN_TEXT_AND_CLAUSES.md)). |
| v6 | — | Intermediate, never committed alone. |
| v7 | 2026-09-23 | Every sentence gets a partner: positional, unconfirmed groups fill the gaps. |
| v8 | 2026-11-17 | Comma, colon and dash clauses refined inside every sentence group, with the margin test. Never committed: a pilot page showed it lumping 16 German chunks with 5 English ones and confirming the lump. |
| v9 | 2026-11-18 | Unconfirmed sentence groups refined as one region; large remainders stay unconfirmed; vector arithmetic in NumPy and each text embedded once per paragraph pair. |

The version is part of each artifact's processor version; v7 artifacts stay in the
database but are no longer read.

## Pilot, 2026-11-18 (LaBSE, v9)

| Pair | Groups | Confirmed | Clause-level | Words per chunk, median / p90 | Paragraph-only |
| --- | ---: | ---: | ---: | ---: | ---: |
| Der Tod in Venedig DE → EN | 2,262 | 95% | 82% | 9 / 20 | 0 |
| Immensee DE → EN | 1,136 | 95% | 72% | 7 / 15 | 0 |
| Jekyll and Hyde EN → DE | 2,324 | 91% | 80% | 9 / 19 | 0 |
| Jekyll and Hyde EN → UK | 2,356 | 96% | 78% | 9 / 19 | 0 |
| Jekyll and Hyde EN → ES | 2,542 | 97% | 82% | 9 / 18 | 0 |
| Candide FR → EN | 3,674 | 92% | 82% | 9 / 18 | 0 |
| Candide FR → DE | 3,640 | 93% | 61% | 9 / 18 | 0 |
| Der Tod in Venedig DE → DE B2 | 2,273 | 93% | 80% | 8 / 19 | 0 |
| Frankenstein EN → EN B2 | 8,242 | 99% | 87% | 8 / 16 | 0 |

v7 on Der Tod in Venedig DE → EN had about 1,000 sentence groups, median 20 words and p90
49. The counts are coverage, not accuracy. Accuracy was read by hand on sampled
paragraphs of each pair: confirmed pairs were right; the misses are chunk boundaries the
two languages draw a few words apart ("Elle ne peut parler," against "“She cannot speak,”
says the maid,"), which the margin test usually catches and leaves unconfirmed. FR → DE
has the lowest clause share because the German often joins two French comma pieces into
one phrase.

## The alignment page

`/editions/<id>/sentence-preview/<other>/` has two views. **Rows** puts each group on its
own line, both sides abreast. **Paragraphs** keeps the text running and gives each group
one tint on both sides: solid where confirmed, a dashed underline where not; pointing at
a chunk outlines its partner. "Unconfirmed · N" filters the rows view to the groups the
aligner did not confirm (older artifacts without that verdict fall back to similarity
below 75%).

## Speed

LaBSE on CPU is the cost: about 1 s per paragraph pair in one process with five threads
after v9 (v8 spent as long again in pure-Python vector arithmetic). The local machine has
no GPU and neither does the deployment host (ARM64, `--concurrency=1` worker), so the
levers are CPU ones:

- Several processes at once, each with a share of the cores; three on the 16-core local
  machine ran the pilot. A deployed equivalent is a separate low-priority worker for this
  task, so a book's alignment never holds a production's queue.
- Embed the shared side once per book, not once per pair: an original with five
  companions embeds its own sentences five times today.
- Embed a whole chapter in one call instead of one paragraph pair at a time, so the
  encoder pads less.
- An int8 ONNX export of LaBSE, which is usually two to three times faster on CPU,
  if a comparison shows the same pairs.

## Open

- Start the job automatically when a production's edition is ready, on its own worker.
- The four speed items above.
- Calibrated accuracy: a hand-labelled sample per language pair, so "confirmed" has a
  measured error rate rather than a reading.
