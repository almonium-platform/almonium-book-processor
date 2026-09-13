# Book pipeline: decision record

**Date:** 2026-09-13
**Status:** decisions, not options. Overrule with a reason.

---

## 1. The edition tree

**Invariant: every derived edition has exactly one parent, and the chain is
monotonic in distance from the author.**

```
Work
└── original (es, C2 computed, C2 editorial)
    ├── modernised (es, C1)          ← one step: lexis and syntax only
    │   ├── B2 adaptation (es)       ← derives from modernised
    │   └── B1 adaptation (es)       ← also from modernised, NOT from B2
    ├── AI translation (uk, period-faithful)
    └── PD human translation (en, inferred alignment)
```

**B1 derives from the same source as B2, never from B2 itself.** Chaining two
AI paraphrases compounds drift and destroys your ability to regenerate one rung
without the other. The vocabulary-subset property you'd gain is not worth
generation loss.

**Adaptations chain from the modernised edition when one exists.** Adapting
raw Cervantes to B2 asks one model call to do two unrelated jobs, and the label
must say which ancestor it came from.

### When to modernise

Two signals, one operator decision. Never automatic.

1. Publication year — pre-1900 is elevated risk, pre-1800 near-certain.
2. Archaism score from chapter analysis — share of tokens the model flags as
   obsolete or no longer current.

If archaism exceeds threshold on a majority of chapters, the edition page
*recommends* modernisation with the evidence. The operator confirms. Period-
faithful Poe is a legitimate product; a modernised Dickens is a small crime.

### How far modernisation goes

**Test: could a writer today have written this sentence, and if not, is the
obstacle the language or the content?**

| Change | Verdict |
|---|---|
| `ere` → `before`, `thou hast` → `you have` | Modernise |
| Obsolete spelling, dead idioms | Modernise |
| Long Victorian subordinated periods | **Keep** — that is style |
| Carriages, valets, social forms | **Keep** — that is setting |
| Imagery, metaphor, sentence rhythm | **Keep** |

Modernisation changes how it is said, never what is said or what is depicted.

### Which levels to generate

**At most two rungs below the source, never below B1.**

- C2 → C1, B2
- C1 → B2, B1
- B2 → B1
- B1 → nothing

Below B1 the adaptation stops being the book and becomes a plot summary with
character names. That is a graded reader, which is a different product and
Beelinguapp's territory, not yours.

### Abridgement

Separate operation, rare, only above ~150k words. **Cut whole scenes and
chapters; never compress prose.** What remains must still be the author's
sentences. Anything else is a retelling and should be labelled as one.

---

## 2. Chapter as a first-class analytical unit

Yes. The model already exists between Edition and ContentBlock; what it lacks
is analysis. Add to Chapter:

- `cefr_estimate`, `cefr_confidence`
- `archaism_score`
- lexical profile (mean sentence length, clause density, band distribution)
- `summary` (2–3 sentences)
- `hard_words` (above the chapter's band)
- `first_encounter_words` — useful words appearing here for the first time in
  the book
- `content_flags`
- `themes`, `setting`

Book level is the **75th percentile of chapter levels**, stored with min, max,
and confidence. The operator's `cefr_level` remains a separate editorial
override column and must never be overwritten by republication.

Within-book variance is large and real — Frankenstein's frame letters and the
creature's monologue are not the same text — so a single book-level badge
without per-chapter data will mislead readers.

---

## 3. CEFR estimation: LLM primary, deterministic as the referee

CEFR is a judgment about communicative complexity, not a formula. Sentence
length and frequency bands correlate with it; they do not constitute it. A text
of short sentences about abstract moral reasoning is not A2. Calibrating
deterministic features properly needs a labelled corpus you do not have and
would have to build by hand.

So:

- **LLM judges**, from the whole chapter.
- **Deterministic features go into the same artifact as evidence**, not as the
  primary signal. They cost nothing and you already compute them.
- **Disagreement of two bands or more raises a review warning.** That is where
  the deterministic path earns its keep.
- Store computed estimate separately from editorial level. Always.

### Feed whole chapters, not snippets

Snippets would suffice if CEFR were all you wanted. It is not. Summary,
archaism, hard words, themes, content flags, and register recommendation all
need the whole chapter, and input tokens are the cheap half. A 5,000-word
chapter is roughly 7k input and 300 output; a 24-chapter book lands well under
a dollar at flash tier with batching.

### What to extract in the same call

Worth taking:

- CEFR with evidence (vocabulary, syntax, register) and confidence
- Archaism score + `modernisation_would_help`
- Chapter summary — feeds SEO, the reader's "previously", and resumption
- Hard words with band
- First-encounter vocabulary
- Themes, setting, named characters — powers recommendation and search
- **Content flags** — period racism, violence, sexual content, suicide. Public-
  domain literature is full of the first, your audience includes teenagers, and
  you want this on file before a parent writes to you rather than after.

Not worth taking here:

- **Comprehension quizzes.** They go stale the instant you adapt the text, they
  test reading comprehension rather than vocabulary, and they are off-mission.
  If you want them later, generate per-edition, not in the analysis stage.
- Difficulty of individual sentences. Too granular to act on.

---

## 4. Adaptation: pass every chapter, tell the model what you found

Do not skip chapters already at the target band.

**Uniform pass, level-aware instruction.** For a chapter already at B2 in a
B2 adaptation, the prompt says so and asks for minimal intervention. You get:

- Consistent voice across the edition — mixing original and adapted chapters
  reads as tonally broken even when each is individually fine
- Uniform provenance labelling, rather than per-block machine-generated flags
- A `blocks_changed` ratio per chapter, which is a QA signal: a chapter that
  changed 2% when the estimator said it was two bands high means something
  failed

The cost of not skipping is a couple of dollars per book. Not a consideration.

---

## 5. "See the original" — yes, as a toggle, not a reading mode

Sustained side-by-side reading of two versions of the same text in the same
language has no pedagogical value. You are comparing paraphrases, not learning.

But a per-paragraph reveal is worth building:

- It earns trust in the adaptation — the reader verifies you did not butcher it
- It is a genuine wow moment and a good screenshot
- It costs nothing; `align_group` already makes it a join
- It doubles as a **ladder prompt**: "You have been reading at B1. Here is this
  paragraph at C1." Nobody else can offer that, and it is a retention mechanic
  rather than a novelty

Gate the toggle, not the reading. The adapted edition is the product; the
original is the reveal.

---

## 6. SEO: one page per chapter

Agreed, and it is the highest-leverage thing the pipeline feeds.

Each chapter page carries: full text in both languages, CEFR, summary, useful
words with frequency, first-encounter vocabulary, and links to adjacent
chapters and other editions of the same work.

One book becomes 24 indexable pages instead of one, and the summary plus word
list is what keeps them from reading as thin duplicate content. The
auto-generated "most useful words in chapter N" list is a second long-tail
surface that falls out for free.

Server-rendered. An Angular SPA will not rank.

---

## 7. Book-sourced examples in Discover

Strong yes, and it needs no IR system.

You already produce every sentence with stable offsets during the sentence
stage. Add one table, populated in the same pass:

```
lemma_occurrence
  lemma, language, edition_id, chapter_id, block_id, sentence_id,
  sentence_cefr, is_first_encounter
  INDEX (lemma, language)
```

A 100k-word book yields roughly 80k rows. Fifty books is four million. That is
an ordinary Postgres index, not a search problem.

Ranking for a lookup, in order:

1. Sentences from the book the learner is currently reading
2. Books in their library or already started
3. Any book in the catalogue, preferring sentences where every other word is at
   or below their level

Then: **link back to the book.** "This word appears in *Der Vorleser*,
chapter 3 — read it there."

This is a real differentiator. "Example sentences from real books you can go
read" beats a generated example sentence decisively, it closes the loop between
Discover and the reader, and it is one of the few features where your content
investment produces compounding product value rather than just catalogue size.

---

## 8. Private imports

**Same ingestion and normalisation. No translation. No adaptation. No parallel
editions. No sharing.**

The legal line here is sharper than the hosting question. Hosting a user's own
copy of a book has safe-harbour arguments. Generating a Ukrainian translation
or a B1 adaptation of a copyrighted novel on your servers is creating a
derivative work, which is precisely what copyright protects and where no
safe harbour helps you.

Private imports get: ingestion, sentence splitting, lexical profile, level
estimate, word lookup, save-to-cards, reading progress. That is a complete and
genuinely valuable product.

**Two consequences.**

First, private imports become almost free — deterministic NLP only, no model
calls beyond level estimation. So **3 per month is too stingy.** Make it a
library cap rather than a rate cap: **10 imported books held at once**, delete
to make room. Easier to reason about and it is storage you are actually
limiting.

Second, add a **"request this for the public library"** action on any import.
If the title is public domain, it routes into your catalogue queue. User demand
then drives your content roadmap instead of your guesses, which is the cheapest
catalogue prioritisation signal you will ever get.

---

## 9. Language support: capability is per (language, feature)

Your instinct is right. Do not limit the language list. 130 on the backend,
support varying underneath.

The mechanism: **capability resolves per feature, at runtime, from a table.**
Not a global tier per language.

```
language_capability
  language, feature, level, provider
```

Features resolved independently: `sentence_split`, `tokenize`, `lemmatize`,
`pos`, `morphology`, `frequency`, `tts`, `translation`, `books_available`,
`collocations`.

So Ukrainian resolves spaCy + wordfreq + TTS + books. Welsh resolves regex
sentence splitting, no frequency, no books, LLM-only lemmatisation. Both work.
Welsh gets a plainer Discover sheet and manual cards, which is a real product.

Three rules:

1. **Never block a language. Degrade.**
2. **Never render a control that will fail.** Hide the feature, do not disable
   it with an error.
3. **Be honest at the picker** — a small support indicator, not a warning that
   blocks.

The LLM is the universal fallback for anything spaCy cannot do. It will
lemmatise Welsh; it just will not do it for free, so cache aggressively.

The spaCy ceiling of ~24 languages genuinely does not constrain you, because
you will not have books in languages spaCy does not cover. Overlapping
constraints resolve naturally when each is expressed as its own capability
rather than as one tier.

---

## 10. Phrase-level alignment

Layer on top of sentence alignment. Pair-specific. Generated only for pairs
someone opens. Cached forever.

**Do not start with an LLM.** Word alignment is a solved NLP problem with free
offline tools. Look at `awesome-align` and `SimAlign` — both use multilingual
transformer embeddings to produce unsupervised word-level alignments. Then
group words into phrases using the dependency parse: a phrase is a subtree
whose aligned counterparts are contiguous on the other side.

Pipeline:

1. Sentence pair from the existing alignment
2. Word-level alignment (offline model)
3. Group into phrases via dependency subtrees
4. Confidence score per group
5. **LLM only for low-confidence groups** — idioms, separable verbs, anything
   where the grouping is genuinely ambiguous

**Store as character ranges on both sides, keyed to sentence IDs.** Never word
indices; a tokeniser change silently corrupts every stored alignment.

A separable German verb maps as one unit with two discontiguous ranges. Make
sure the schema allows multiple ranges per side from the start.

---

## 11. Bugs and gaps to close before anything above

| Issue | Why it matters |
|---|---|
| Backend `cefrLevel` is NOT NULL, processor allows null | Publication fails or writes garbage |
| Republication overwrites operator-corrected level | Editorial work silently lost |
| Editorial level and computed estimate share one column | Cannot ever compare them |
| `UserErrorReport` is a model with no workflow | Your only QA on machine translation at scale |
| No language-mismatch QA gate | A mislabelled EPUB ships as the wrong language |
| No chapter-size gate | Split failures publish silently |
| Register stored inside the translator string and re-parsed | Make it a column |

---

## 12. The thing worth saying plainly

The pipeline is now more finished than the reader.

Frankenstein exists in Ukrainian at 815 of 815 aligned blocks, with provenance,
cost accounting, and a tombstone if you delete it. There is no public page
where a stranger can read a single paragraph of it.

Everything in this document is correct work. None of it is the next work. The
next work is one server-rendered chapter page with that Ukrainian text beside
the English, indexable, with a sign-up card at the bottom.
