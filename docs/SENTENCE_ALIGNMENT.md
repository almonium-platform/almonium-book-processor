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

The pipeline **queues it by itself** (`catalog/sentence_alignment_queue.py`): when a
translation's or adaptation's sentences are split, its pair with the original is
queued; when an original's sentences change, every edition made from it is. Only
public works; a pair already current, queued or running is left alone. Staff can still
start one from the alignment page. The job runs on its own Celery queue
(`SENTENCE_ALIGNMENT_QUEUE`, "alignment") and container, `aligner`, so a book's minutes
of alignment never hold the worker the productions' local steps run on.
`manage.py queue_sentence_alignment [--dry-run] [--work <slug>]` catches up books that
existed before (403 pairs on 2026-11-18), original by original so each original is
embedded once. Alignment artifacts travel with promotion bundles, so aligning where the
books are produced is enough.

A killed run (worker restart) is closed by the janitor after two hours of silence, like
the other one-process jobs, and starting it again resumes: every finished paragraph
comes back from its artifact.

## How v10 matches

1. spaCy sentence spans on both sides; LaBSE embeds the sentences; a monotonic dynamic
   programme over cosine similarity proposes 1:1, 1:2, 2:1, 2:2, 1:3 and 3:1 groups with a
   small length prior. A group is confirmed at similarity ≥ 0.82, or ≥ 0.75 when it beats
   every crossing alternative by 0.10. Gaps get positional groups, unconfirmed. Paragraphs
   of up to 600 sentences a side are matched this way (v9 stopped at 80).
2. Every sentence is cut into clause chunks at `;` (two words a side suffice) and at
   `,` `:` `—` `–` `--` (four words a side), never rewriting text or offsets.
3. Confirmed sentence groups are refined one by one. **Consecutive unconfirmed groups are
   refined together as one region**, because an unconfirmed group usually means the two
   languages put a sentence boundary in different places, and a chunk must be free to
   find its partner across it.
4. Inside a group or region, the same dynamic programme pairs chunks. A chunk pair stands
   when its similarity is ≥ 0.6 **and** it beats, by ≥ 0.2, the crossing pairings of the
   groups up to six places either side (every chunk of 99.4% of sentences); the weakest
   pair otherwise merges with the neighbour it fits best, and this repeats until every
   pair stands or one group is left (then the sentence groups are kept as they were).
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
| v10 | 2026-11-18 | Sentence matching up to 600 sentences a side, not 80; a chunk pair competes with its neighbours, not the whole region. Same result as v9 on 160 of 160 sampled ordinary paragraphs. |

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

## A model reads what stayed unconfirmed

Running the offline aligner again gives the same answer, so the stretches it leaves
unconfirmed (8% of groups in v9, in 28% of paragraph pairs) need a different judge.
`catalog/sentence_adjudication.py` shows a model each maximal run of unconfirmed groups
in a paragraph pair, as numbered clauses, and takes back their grouping with a verdict
per group. Confirmed groups are never sent and never change.

- **Run it** from the host, where the plans are signed in:
  `./plan-manage adjudicate_sentence_alignment [--dry-run] [--sample N] [--work <slug>]
  [--model <model or seat>] [--workers N] [--apply-only]`. Nothing queues it.
- **Model**: `SENTENCE_ADJUDICATION_MODEL` (default `gpt-5.6-luna`), a bare model, so it
  runs on a plan where `AI_PLANS` has one that serves it.
- **Bought once**: a stretch's judgment (`AlignmentJudgment`) is keyed by the adjudication
  version, the model, the two languages and the stretch's clause texts. No block, edition,
  run or offline version is in the key, so a later offline version or a re-ingested book
  finds every stretch whose clauses did not change. Switching models reuses usable judgments
  and carries over failed attempts for the same adjudication version. About twelve stretches share a call;
  a call that was paid for and killed before its answers were kept is read from the
  ledger. An answer that does not cover its stretch is asked once more and then left. A
  refused allowance stops the pass and counts as no attempt.
- **Result**: a second `sentence_alignment` artifact under the same pair hash, processor
  version `sentence-adjudication-v1:<model>` (or `sentence-adjudication-v1:mixed` for a
  paragraph judged by several models), holding the offline payload with the judged
  stretches' groups replaced (`acceptance: llm_adjudication`, no similarity). The reader
  (`parallel_content.inherited_payload`) serves it in place of the offline artifact it was
  made from (`adjudication.base`) and of no other. After a text correction or a new offline
  version, `--apply-only` rewrites the artifacts from the judgments already paid for.
- Stretches longer than 40 clauses a side are not asked (31 in the library).

### Sample, 2026-11-18 (claude-sonnet-5-5 on the Claude plan)

200 paragraphs spread over 100 edition pairs: 260 stretches in 101 calls, about three
seconds each, $0.035 of the plan. 246 answered, 14 answers did not cover their stretch.
In the answered stretches 276 unconfirmed groups became 375, of which 340 (90%) the model
confirmed. Read by hand on 45 stretches: the confirmed groups were right, and the ones it
left unconfirmed were real differences (an adaptation that adds a sentence, a clause with
half its content on the other side). Much of the offline doubt was punctuation: a French
guillemet or a Spanish dash split off as its own "sentence".

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

## The review of 2026-11-18

The v9 backfill stalled on Der Prozess: a paragraph of 234 pairs ran for half an hour.
Nothing had been timed on the library's largest paragraphs, only on samples. What the
review found, worst first:

- **Paragraphs over 80 sentences were never sentence-matched.** One hundred of them
  (most of Der Prozess, Emma c50.p13, Pride and Prejudice c3.p91) became a single region
  of up to 670 chunks, and the margin test against the *whole* region merged every pair
  away: v9 confirmed none of their groups. v10 matches their sentences first and compares
  a chunk only with its neighbours: Der Prozess c5.p4 went from 0 to 395 of 438 groups
  confirmed.
- **Cubic and quadratic loops in pure Python.** The chunk merge recomputed every margin
  from scratch after each merge (n³); the dynamic programme took a Python mean and cosine
  per cell; pooling a long text's pieces scanned every piece for every text, which the
  2,048-text look-ahead calls made quadratic. All three keep their arithmetic and now run
  as matrix operations: the worst paragraph matches in 1.1 s, not 25+ minutes.
- **NumPy's OpenBLAS spun a thread per core** for each small product: three aligner
  processes held 13 cores. One thread is as fast (`OPENBLAS_NUM_THREADS=1` on the aligner).
- **The worker cache stored float64 and never refreshed on a read**, so a full cache could
  push out the original's text a second companion was about to use. Now float32
  (half the memory) and least-recently-*used* goes first.

The lesson kept here: time and read the library's largest paragraphs, not a random
sample, before a full run.

Not changed: French spaCy makes a lone "«" its own sentence (harmless to alignment);
under Modal each process still loads the whole model to tokenize (about 330 MB more than
the tokenizer alone).

## The library backfill, 2026-11-18 (v10)

All 412 pairs (every public translation or adaptation with its original) aligned in
1 h 44 min, 19:50–21:34, with no failure: 683,820 paragraph pairs, 3,171,262 groups,
**91.8% confirmed**, 69.1% at clause level. 258,765 groups stayed unconfirmed (8.2%), in
27.1% of paragraph pairs: 140,433 sentence matches under the bar, 111,235 clause pairs in
unconfirmed stretches, 5,351 placed by position. 1,961 paragraph pairs have no groups,
reported as `missing_sentences`: all of them are textless blocks both editions keep, 1,310
scene-break separators and 651 images. Nothing is missing; there is no text to match.

What set the pace, measured during the run on an 8-core laptop with embeddings on Modal:

- **Waiting, not computing.** Four aligner processes used 45–90% CPU in all. A Modal call
  for 2,048 texts took 4–6 s warm (19–33 s cold), most of it the vectors coming back;
  matching those paragraphs takes about as long. A look-ahead thread now fetches the next
  window while the current one is matched (`86dcb76`, with a test that fails on a
  sequential loop), and six processes run instead of four (`ALIGNER_CONCURRENCY`, the
  tokenizer-only load making room): 79–91 → 135 paragraph pairs a second.
- **Bandwidth.** Six processes pulled 57 Mbit/s. Vectors now come back as float16
  (`88604a0`; the app answers float32 to an older worker): a lone warm call went from
  4.2–6.2 s to 3.5–5.3 s. The gain under six-way concurrency was not measured; the
  backfill had finished.

## Open

- Re-promote the aligned books: alignment artifacts reach staging and production only
  in a promotion bundle, and these were promoted before they were aligned.
- Speed: embed each original once for all its companions (one task per family), now
  that the transfer, not the matching, sets the pace. The deployment host is measured in
  [MODAL.md](MODAL.md): about 25 texts/s on its CPU against about 500 on Modal.
- Calibrated accuracy: a hand-labelled sample per language pair, so "confirmed" has a
  measured error rate rather than a reading.

## Punctuation-only sentences, 2026-11-18

spaCy's small models gave a lone «, » or dialogue dash a sentence of its own: 125,954 of
879,739 French sentences (14.3%), 23.7% of Italian and 7.8% of Portuguese ones, 1-4% in
several other languages. `processing/punctuation.py` keeps the one inventory of quotation
and dialogue marks per language (German and Danish set »…« pointing inward, so » opens
there and closes in French) and folds each such piece into the sentence it belongs to: a
mark set against text without a space goes with that text, otherwise opening marks and
dashes go with what follows and closing marks with what came before. Sentence splitting
does this as it splits (`a59a997`); `manage.py repair_sentence_punctuation` folded the
existing blocks in place and re-queued the alignment of the pairs they are in. 368 French
pieces remain, each a whole paragraph of marks (decorative rules, dot leaders, scene
breaks) with no sentence to join.
