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

Measured 2026-11-18 on the local machine (AMD Ryzen 7 7840HS: 8 cores, 16 threads,
AVX-512, no GPU), v9, LaBSE, nothing else running. The deployment host (ARM64, no GPU,
`--concurrency=1` worker) has not been measured.

**Where the time goes** (72 sampled paragraph pairs from six language pairs, 5 threads,
0.66 s per pair on average):

| Part | Share |
| --- | ---: |
| LaBSE forward pass | 92% |
| Tokenizing and pooling | 2% |
| Sentence matching | 3% |
| Chunk matching and merging | 3% |

**Model throughput** (texts per second, a fixed mix of sentences and clause chunks):

| Setting | Texts/s |
| --- | ---: |
| As called today: one call per paragraph pair (~16 texts), fp32, 5 threads | 27–41 |
| One large call, batches of 32, fp32, 5 threads | 70 |
| Batches of 64 / 128 instead of 32 | 61 / 49 |
| fp32, 1 / 2 / 4 / 8 threads | 17 / 32 / 47 / 61 |
| fp32, 16 threads (hyper-threads) | ~20 (slower) |
| Three processes × 2 threads at once, combined | 61 |
| bf16 autocast, 4 threads | 100 |
| bf16 autocast, 8 threads, batches of 32 | 130 |

The machine caps at about 60 texts/s in fp32 however the threads are split among
processes, so parallel workers do not help here; bf16 does. bf16 vectors agree with
fp32 at cosine ≥ 0.9968; over the 72 paragraph pairs, 71 came out identical and 1 of
584 groups changed. PyTorch dynamic int8 quantization did not apply to this model
(output identical, slower); int8 would need ONNX Runtime.

**Repeated work:** pairing every derived edition with its original embeds about 12.3
million texts for the library (412 pairs, 115 works); embedding each edition once and
reusing it across its companions needs 8.1 million, 34% less.

**Implemented 2026-11-18** (`a1fa836`): device and precision from the hardware (bf16 only
where native, fp32 otherwise, a GPU when visible; `NLP_EMBEDDING_*` overrides), look-ahead
calls of 2,048 texts, and a worker cache so an original is embedded once for all its
companions. Jekyll and Hyde, 352 paragraphs: EN → DE 158 s → 80 s; the next companion,
EN → UK, 134 s → 40 s. Against the old fp32 path, 700 of 704 paragraphs came out identical
and about 6 of 4,680 groups differed.

**Whole library** (686,000 paragraph pairs):

| Setting | Time |
| --- | ---: |
| Today (0.66 s a pair) | about 126 h |
| One call per chapter + bf16 + 8 threads + each edition embedded once | about 17 h of model time plus about 10 h of matching, which a second process overlaps |
| A rented GPU for the embeddings | not measured here; the matching (about 10 h on one core, splittable across processes) becomes the floor |

## Open

- Start the job automatically when a production's edition is ready, on its own worker.
- Speed: measure the deployment host (ARM64, no native bf16 on Neoverse N1: fp32 there).
- Calibrated accuracy: a hand-labelled sample per language pair, so "confirmed" has a
  measured error rate rather than a reading.
