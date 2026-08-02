# Almonium ebook pipeline

**Date:** 2026-07-28
**Scope:** ingestion, normalisation, translation, adaptation, alignment, QA,
audio, and the admin surface around all of it.

---

## 1. Architecture

Two separate things that both happen to be Python. Do not merge them.

**A. The pipeline (offline, batch, no HTTP).**
A CLI plus a worker queue. Runs on your Oracle box or your laptop. Ingests,
transforms, and publishes book editions. Nothing user-facing ever waits on it.
Output lands in Postgres and object storage.

**B. The NLP service (online, internal HTTP).**
FastAPI on localhost, called by the Java monolith. Lemmatisation, POS,
morphology, tokenisation, sentence splitting, phrase-template matching. Never
exposed publicly; bind to 127.0.0.1 and call it from Java.

They share a library (models, tokenisers, language adapters) and nothing else.

**Is Python right?** Yes, uncontested. `spaCy`, `sentence-transformers`,
`ebooklib`, `BeautifulSoup`, `pysbd`, `wordfreq`, `simplemma` have no real
equivalents on the JVM. This is the one place where a polyglot stack earns its
keep.

**Deployment:** systemd unit for the FastAPI service, a second unit for the
worker. Load spaCy models once at startup, not per request. Budget ~1.5GB RAM
for DE+EN models loaded simultaneously.

---

## 2. Input formats: EPUB first, TEI when available

Your current HTML-from-Gutenberg approach works but it does not compose.

**Decision: EPUB is the primary user-upload input. TEI P5 XML, including ELTeC,
is a first-class curated-catalogue input.** Both normalize into the same block
schema. Reasons:

1. It is structured. Spine order, chapter boundaries, and metadata are declared
   rather than inferred from `<h2>` heuristics.
2. **It is the same code path as user uploads.** Every hour spent hardening
   EPUB ingestion serves both your catalogue and your premium import feature.
   HTML scraping serves only you.
3. Sources are richer: Standard Ebooks, Gutenberg's own EPUB exports,
   Wikisource exports, and whatever a user drops in.
4. TEI sources already declare divisions, headings, paragraphs, verse, notes,
   quotations, and scholarly metadata. Preserving that structure is better than
   converting it to EPUB or flattening it before ingestion.

Keep an HTML adapter for the sixteen books you have already done. Do not
rewrite them; write a one-time migration into the normalised format.

## 3. Your custom format: keep it, but change what it is

Your current markup (`div.book` → `div.header` → `div.chapter` → `p.pfirst`
with `span.dropcap`) is decent. The problem is that it is doing two jobs:
storage and presentation.

**Split them.**

**Storage:** normalised JSON, one row per block, in Postgres.

```json
{
  "edition_id": "remarque-im-westen-de-orig",
  "block_id": "c3.p14",
  "chapter": 3,
  "seq": 14,
  "type": "paragraph",
  "text": "Ich nicke. Wir werfen uns in die Brust...",
  "sentences": [
    {"id": "c3.p14.s1", "start": 0, "end": 9},
    {"id": "c3.p14.s2", "start": 10, "end": 47}
  ],
  "align_group": 218
}
```

`type` is the important field: `paragraph`, `heading`, `verse_line`,
`verse_stanza`, `blockquote`, `letter`, `epigraph`, `dialogue`, `footnote`,
`image`, `separator`. Each one gets different treatment downstream.

**Presentation:** your reader renders from JSON. Dropcaps, first-paragraph
styling, and everything cosmetic becomes the reader's job, not the data's.

Why this matters: alignment, translation, adaptation, TTS timing, and word
lookup all need stable block and sentence IDs. Cosmetic HTML classes cannot
carry that. Version the schema from day one (`schema_version: 1`).

## 4. The alignment graph, and the granularity you asked about

You are right that the canonical-group approach constrains granularity, and
right that phrase colouring is the exception. Here is the clean split.

**Layer 1 — canonical alignment groups (N editions, not N²).**
Every edition of a work aligns once against a canonical block sequence. Group
218 might be paragraph 91 in the English, paragraphs 88–89 in the German, and
paragraph 94 in the French. The client composes any pair on demand. Cost is
linear in editions.

Granularity: paragraph, and sentence within a paragraph where the split is
clean. This is enough for synchronised scrolling and side-by-side reading,
which is 95% of the value.

**Layer 2 — phrase-level colouring (pair-specific, cached, on demand).**
Sub-sentence correspondence genuinely cannot be composed transitively.
DE→EN→FR phrase mapping degrades badly. So generate it per pair, per chapter,
only for pairs someone actually opens, and cache it forever. Your existing
"request a pair" infrastructure is exactly the right gate for this.

**Alignment method, cheapest first:**

1. Split into sentences (`pysbd`, or spaCy's sentenciser).
2. Embed both sides with a multilingual model (LaBSE or a
   `sentence-transformers` multilingual variant).
3. Dynamic programming over cosine similarity with 1:1, 1:2, 2:1, and 0:1
   transitions. Gale–Church length priors as a fallback signal.
4. Flag spans below a confidence threshold.
5. **Only** the flagged spans go to an LLM.

Expect 90–95% clean on a professionally translated novel, and much worse on
loose or abridged translations. That failure rate is the argument for the
admin panel below.

---

## 5. Human translation vs machine: the decision tree

```
Is a good PD human translation available in the target language?
├── Yes, and it is readable modern prose
│     → use it. Free, better register, no disclosure needed.
├── Yes, but it is 1890s archaic prose
│     → use it only if the original is also period prose.
│       A 1900 English Dostoevsky next to modern Ukrainian reads wrong.
└── No
      → LLM translation, disclosed.
```

**Where to look for PD human translations:**

- **Project Gutenberg** — has non-English sections, and English translations of
  European classics. Uneven but free and legally clean in the US.
- **Wikisource** — per-language subdomains, many PD translations, structured
  and API-accessible.
- **Standard Ebooks** — English only, but the cleanest markup available. Use as
  the canonical English edition wherever a title exists.
- **ELTeC (European Literary Text Collection)** — TEI-encoded 19th-century
  novels across a dozen European languages, built for research, openly
  licensed. Underused and well-suited to exactly your use case.
- **Projekt Gutenberg-DE** — German texts, but the licensing is *not* the same
  as Project Gutenberg's. Check per text before using commercially.

**The honest constraint:** modern translations of anything are under copyright
for decades. PD human translations skew pre-1930. That is why LLM translation
is not a shortcut, it is the only route to contemporary-register parallel text.

## 6. LLM vs DeepL for book translation

Run the arithmetic on a 100,000-word novel (~600,000 characters, ~140k input
tokens, ~180k output tokens).

| Method | Cost per novel per language |
|---|---|
| DeepL API | ~$15 at $25/M characters |
| Google Cloud Translation (NMT) | ~$12 at $20/M characters |
| Google LLM Translation mode | ~$6 at $10 in + $10 out per M |
| LLM, budget tier ($0.60/$2.40) | ~$0.50 |
| LLM, mid tier ($3/$15) | ~$3 |

DeepL costs five to thirty times more and gives you less. It cannot take a
style brief, cannot preserve your block IDs, cannot hold chapter context, and
cannot produce level-adapted output at all. Note also that DeepL's API Free and
API Pro plans were retired in July 2026, so verify current plan structure before
budgeting anything.

**Decision: LLM for books. Batch API for the 50% discount. Mid-tier model.**
Reserve DeepL for short runtime lookups if you ever want a second opinion on a
phrase, and even there an LLM with the surrounding sentence usually wins.

Which model: translate one chapter with two or three candidates, then judge
blind. Do not pick on benchmarks; literary register is not what SWE-bench
measures. Send me chapter output and I will assess it — that is a good use of a
frontier model and a bad use of your evenings.

## 7. Abridgement and level adaptation

You are right about Don Quixote. Some books are unreadable in the original for
reasons that have nothing to do with the learner's level.

Three distinct operations, and you should keep them distinct:

| Operation | What changes | When |
|---|---|---|
| **Modernisation** | Archaic syntax and lexis, same length, same content | Old-language originals (Cervantes, Shakespeare, early Goethe) |
| **Level adaptation** | Vocabulary and sentence complexity capped at a CEFR band, ~same length | Any book, to create the B1/B2/C1 ladder |
| **Abridgement** | Length cut, subplots removed | Very long novels only |

Do not chain all three blindly. A B1 abridged modernised Don Quixote is a
different book, and you should say so.

**Label everything.** `edition_type`, `source_edition_id`, `cefr_level`,
`model`, `prompt_version`. Show it in the reader.

## 8. Handling messy input

Your instinct that the pipeline will fail is correct. Build for it.

**Confidence gates at every stage.** Each stage emits a score and a list of
warnings. Anything below threshold goes to a review queue rather than
publishing.

Concrete checks worth having:

- chapter count within expected range, and monotonic
- no chapter under 200 words or over 20,000 (usually a split failure)
- detected language matches declared language, per chapter
- paragraph count between editions within 25% of each other
- alignment: no run of more than three consecutive low-confidence groups
- no unclosed markup, no stray Gutenberg licence boilerplate
- translated chapter length within 60–160% of source (catches truncation and
  runaway generation)
- sentence count preserved within tolerance after adaptation

**Idempotency.** Every artifact keyed by
`(source_hash, stage, processor_version, model, prompt_version)`. Rerunning a
stage with the same inputs is a no-op. This is what lets you fix one prompt and
reprocess only what it touched.

## 9. The admin panel: yes, build it

Not overthinking. You will spend more time fixing books than writing pipeline
code, and doing that through SQL will make you stop doing it.

**Minimum viable version, one weekend:**

- List editions with status, stage, and confidence
- Chapter view showing source and target side by side, with low-confidence
  alignments highlighted
- Edit a translated paragraph in place
- Drag to re-pair a misaligned group
- Publish / unpublish an edition
- Inbox of user-reported errors

Skip everything else. No analytics, no charts, no user management. Server-
rendered HTML is fine; nobody but you will see it.

**User error reporting: yes.** A small flag icon on any paragraph. It costs a
day and it turns your readers into unpaid QA on machine-translated text, which
is the single largest quality risk in the whole product. It also signals that
you take the text seriously.

## 10. Disclosure

**Yes, disclose. Always, and prominently.**

Not primarily a legal question, though the EU AI Act's transparency provisions
point the same way. It is a trust question with an audience of literary-minded
language learners who will notice anyway.

Frame it as craft rather than apology:

> **Translation:** machine-assisted, reviewed. Model: X. Spot a mistake?
> Tap to report it.

Undisclosed AI text that a reader catches costs you that reader permanently.
Disclosed AI text with a report button makes them a contributor.

## 11. Special content

| Element | Treatment |
|---|---|
| **Verse** | Block type `verse_line`. Preserve line breaks absolutely. Do not translate line-for-line with an LLM; it will pad. Align at stanza level, never at line level. |
| **Illustrations** | Support them. They are usually PD alongside the text, they make the reader feel like a book rather than a text dump, and they cost nothing. Store as blocks with `type: image`, keep captions as separate translatable blocks. |
| **Footnotes** | Separate block type, rendered as tappable. Never inline into the paragraph text; it wrecks alignment. |
| **Letters, epigraphs, telegrams** | Own block types. They carry register shifts a learner should see. |
| **Chapter titles** | Translate, align, but keep out of the sentence alignment graph. |
| **Dialogue** | No special type needed, but preserve quote marks per language convention (German `„…"`, French `« … »`). An LLM will get this wrong unless you ask. |

## 12. Covers

**Do not use AI-generated covers.** Your audience is literary, and this is
precisely the demographic that reacts badly to AI art. It also contradicts the
paper-warm, bookish identity you have built.

**Use typographic covers.** Title, author, and a colour field in Libre
Baskerville on your cream ground. Generate them programmatically from
metadata: forty covers in an afternoon, visually consistent, free, no legal
risk, and they will look better than AI covers because they will look
deliberate.

Standard Ebooks also publishes PD artwork covers you can reference for which
public-domain paintings pair with which titles.

## 13. Audio

**Do it, but late, and for a handful of books.**

Sentence-level playback needs timing data, and there are two routes:

1. **TTS with timestamps.** Several providers return character or word-level
   timing alongside the audio. Cleanest option: you get audio and alignment in
   one call.
2. **Forced alignment.** Generate audio however, then align it to your text
   with WhisperX or `aeneas`. Works with human audiobook recordings too, which
   matters if you ever license real narration.

Route 1 for machine narration, route 2 for anything else.

**Cost reality:** TTS is the only thing in your stack that scales linearly and
does not amortise across users cheaply. A full novel is many hours of audio.
Readlang's pricing tells you they learned this: their tiers gate audio at ten
hours and two hundred hours respectively. Copy that lesson.

**Recommendation:** generate audio for three or four books, put it behind
premium, measure whether anyone uses it before generating a fortieth.

## 14. Choosing the first books

Not 42. **Eight to twelve**, done exceptionally, in one target language.

**Hard filters:**

- Public domain in the US *and* in the EU (author died 70+ years ago covers
  both)
- Under 120,000 words in the original
- Prose, not verse, for the first batch
- A PD translation exists in at least one of your bridge languages, or the book
  is short enough that LLM translation is cheap to QA

**Ranking criteria, in order:**

1. **Would your target learner choose this?** A Ukrainian learning German wants
   Remarque, Kafka, Zweig, Hesse, Fontane. Not *The Wonderful Wizard of Oz*.
2. **Search volume.** People search "Die Verwandlung English German parallel
   text". Nobody searches for obscure titles. Your SEO strategy lives here.
3. **Sentence-level translatability.** Dense modernist prose aligns badly.
   Hemingway-style short declaratives align beautifully.
4. **Level spread.** You want at least two books that are genuinely readable at
   B1 without adaptation.
5. **Cultural pull for the wedge.** Remarque and Zweig carry weight in the
   Ukrainian reading tradition that Austen does not.

**A concrete starting shelf for DE, with UA and EN bridges:**

Kafka *Die Verwandlung* (short, famous, high search volume, clean sentences) ·
Kafka *Der Prozess* · Remarque *Im Westen nichts Neues* (you already have it) ·
Zweig *Schachnovelle* · Hesse *Siddhartha* · Fontane *Effi Briest* ·
Grimm *Kinder- und Hausmärchen* (selected tales — short, gradeable, excellent
for B1) · Storm *Der Schimmelreiter* · Schnitzler *Leutnant Gustl*.

Verify PD status per title in every territory you serve. Some of these are
clear, some depend on death dates you should check rather than assume.

Do these nine properly, with two level-adapted editions each, before adding a
tenth.

---

## 15. Prompts

Placeholders in `{BRACES}`. Version every prompt and store the version with the
output.

### 15.1 Translation

```
SYSTEM
You are a literary translator working from {SOURCE_LANG} into {TARGET_LANG}.
You are translating "{WORK_TITLE}" by {AUTHOR}, published {YEAR}.

Your translation will be displayed beside the original for language learners,
paragraph by paragraph. Structural fidelity therefore matters as much as
fluency.

REGISTER
- Target register: {REGISTER}
  (options: contemporary neutral | period-faithful | lightly modernised)
- Preserve the author's sentence rhythm. Where the original uses long
  subordinated periods, do not break them into short sentences.
- Preserve dialogue voice: dialect, register shifts, and idiosyncratic speech
  must survive.
- Use {TARGET_LANG} conventions for quotation marks and dashes.

STRUCTURAL RULES — these are absolute
- Return exactly one output block for every input block, in the same order.
- Never merge two input blocks. Never split one input block into two.
- Preserve sentence count within a block wherever the target language permits.
  If you must deviate, deviate by at most one sentence and set
  "sentence_count_changed": true for that block.
- Never add explanatory content, translator's notes, or clarifying phrases
  that are not in the source.
- Never omit a clause because it is difficult.
- Leave proper nouns untranslated unless {TARGET_LANG} has an established
  conventional form.
- Preserve emphasis markers exactly as they appear.

CONTEXT
Preceding block (for continuity, do not translate):
{PREV_BLOCK}

OUTPUT
Return JSON only. No prose, no markdown fences.
{
  "blocks": [
    {
      "block_id": "<echo the input block_id>",
      "text": "<the translation>",
      "sentence_count_changed": false,
      "confidence": 0.0-1.0,
      "note": "<only if confidence < 0.7: what was difficult>"
    }
  ]
}

USER
{BLOCKS_JSON}
```

Feed 10–20 blocks per call. Smaller loses context, larger degrades structural
compliance.

### 15.2 Level adaptation

```
SYSTEM
You are adapting "{WORK_TITLE}" by {AUTHOR} in {LANGUAGE} so that a learner at
CEFR level {TARGET_CEFR} can read it.

WHAT TO CHANGE
- Replace vocabulary above {TARGET_CEFR} with the most natural equivalent at or
  below that level, unless the word is: a proper noun, central to the plot, or
  repeated often enough that the reader will acquire it from context.
- Simplify sentence structure: at most {MAX_CLAUSES} clauses per sentence.
- Reduce sentence length toward {TARGET_SENTENCE_LENGTH} words on average.
- Replace archaic or obsolete constructions with current usage.

WHAT NOT TO CHANGE
- Plot, events, and their order.
- Narrative voice and tone. A simplified text must still sound like this author.
- Direct speech attribution.
- Chapter and paragraph boundaries.
- Approximate length. Do not summarise. Aim for {MIN_RATIO}–{MAX_RATIO} of the
  original word count per block.

FORBIDDEN
- Do not add explanation of what a character means.
- Do not flatten metaphor into literal statement unless the metaphor depends on
  vocabulary far above {TARGET_CEFR}.
- Do not modernise setting, technology, or social detail.
- Do not remove ambiguity the author intended.

ALLOWED VOCABULARY GUIDANCE
These words appear in the source and are above {TARGET_CEFR}. Keep the ones
marked KEEP, replace the rest:
{VOCAB_DECISIONS}

OUTPUT
Return JSON only, one output block per input block, same order.
{
  "blocks": [
    {
      "block_id": "<echo>",
      "text": "<adapted text>",
      "words_replaced": ["<original> -> <replacement>"],
      "confidence": 0.0-1.0
    }
  ]
}

USER
{BLOCKS_JSON}
```

### 15.3 Alignment adjudication (low-confidence spans only)

```
SYSTEM
You are aligning a {SOURCE_LANG} text with its {TARGET_LANG} translation for
side-by-side display.

You will receive a window of sentences from each side. An automatic aligner was
uncertain here. Decide which source sentences correspond to which target
sentences.

Alignments may be 1:1, 1:many, many:1, or 0:1 / 1:0 where a translator added or
omitted material. Do not force a one-to-one mapping.

OUTPUT
Return JSON only.
{
  "pairs": [
    {
      "source_ids": ["s12"],
      "target_ids": ["t11", "t12"],
      "confidence": 0.0-1.0,
      "relation": "equivalent | expanded | condensed | omitted | added"
    }
  ],
  "needs_human_review": false
}

USER
Source: {SOURCE_SENTENCES}
Target: {TARGET_SENTENCES}
```

### 15.4 Phrase-level colour mapping (premium pairs only)

```
SYSTEM
Map corresponding phrases between an aligned {SOURCE_LANG} sentence and its
{TARGET_LANG} translation, so a language learner can see which part means which.

RULES
- Map meaningful units: noun phrases, verb groups, prepositional phrases,
  idioms as wholes.
- Do not map function words that have no counterpart.
- A German separable verb maps as one unit even when split across the sentence:
  return multiple character ranges for that unit.
- Where word order differs, the mapping is still correct. Do not force
  monotonic order.
- If a phrase has no clean counterpart, omit it rather than guessing.

OUTPUT
Return JSON only. Character offsets are into the sentence strings as given.
{
  "mappings": [
    {
      "source_spans": [[0, 12]],
      "target_spans": [[0, 9], [45, 52]],
      "type": "verb_group",
      "confidence": 0.0-1.0
    }
  ]
}

USER
Source: {SOURCE_SENTENCE}
Target: {TARGET_SENTENCE}
```

### 15.5 Structured lexical entry (Discover cache warming)

```
SYSTEM
Produce a lexical entry for a language learner whose fluent languages are
{FLUENT_LANGS} and who is learning {TARGET_LANG}.

The word appears in this sentence, and the entry must describe the sense used
HERE, not every sense in the dictionary:
{SOURCE_SENTENCE}

OUTPUT
Return JSON only.
{
  "lemma": "",
  "surface_form": "",
  "pos": "",
  "morphology": {},
  "sense_here": {
    "definition_in_target_lang": "",
    "translations": { "<lang>": "<translation>" },
    "register": "neutral | formal | colloquial | literary | archaic | vulgar",
    "notes": ""
  },
  "other_senses": [ { "definition": "", "how_it_differs": "" } ],
  "collocations": [ { "pattern": "", "gloss": "", "frequency": "common|occasional" } ],
  "confusable_with": [ { "word": "", "why": "" } ],
  "example_sentences": [ { "text": "", "translation": "" } ],
  "cefr_estimate": "A1|A2|B1|B2|C1|C2",
  "worth_learning_note": ""
}

Rules
- "confusable_with" should list words a {FLUENT_LANGS} speaker specifically
  confuses with this one: false friends, similar forms, overlapping senses.
- Example sentences must be natural and no harder than the word itself.
- If unsure of a field, omit it. Never invent a collocation.

USER
Word: {WORD}
```

---

## 16. Build order

1. Normalised block schema plus EPUB and TEI ingesters. Migrate your 16 books into it.
2. Sentence splitting and embedding-based alignment for one pair (DE↔EN).
3. Confidence gates and a review queue.
4. Admin panel, minimum version.
5. LLM translation for one book into UA. Judge the output before scaling.
6. Level adaptation for one book. Judge again.
7. Publish nine books as public, server-rendered, indexable pages.
8. Phrase colouring on demand.
9. Audio for three books, behind premium.

Steps 1 through 4 are infrastructure and will feel slow. Step 7 is the one that
brings strangers. Do not let steps 8 and 9 jump the queue.
