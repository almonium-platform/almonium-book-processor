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

Status, 2026-09-18: the register is a column (`Edition.literary_register`,
migration 0021) and the editorial level is separate from the computed estimate
(P1-2). The language-mismatch and chapter-size gates and the `UserErrorReport`
workflow are still open. The `cefrLevel` nullability and the republication
overwrite need a check against the current backend before they are closed.

---

## 12. The thing worth saying plainly

The pipeline is now more finished than the reader.

Frankenstein exists in Ukrainian at 815 of 815 aligned blocks, with provenance,
cost accounting, and a tombstone if you delete it. There is no public page
where a stranger can read a single paragraph of it.

Everything in this document is correct work. None of it is the next work. The
next work is one server-rendered chapter page with that Ukrainian text beside
the English, indexable, with a sign-up card at the bottom.

---

## 13. The adaptation floor is found per book, never promised

**Decided 2026-09-18.** We do not force a book down to a level by abridging
it. An adapted edition keeps every proposition, image and degree of certainty
of the original; the level it lands at is whatever that constraint allows.

Evidence that settled it, on Frankenstein: five B1 prompt versions and a
Terra high-reasoning run all judged B2 by a judge that passes calibration
(known B1 → B1, published B2 → B2, original → C1); the published B2 edition
is B2 in 32 of 32 windows, so there is no hidden B1 core; adapting the B2
edition to B1 in a second pass still judges B2 and adds a material meaning
change on top of the minor drift (`docs/evidence/b1-20260918/`). Pushing
harder trades fidelity for a label, and the label is the thing we must not
sell. Full record in [ADAPTATION_PILOT.md](ADAPTATION_PILOT.md).

Consequences:

- **`adapts_to` is per-book metadata**, discovered by pilots and recorded
  with their evidence, and it is the lowest level a faithful adaptation of
  that book reached its gates at (blind difficulty judge at target, fidelity
  audit clean or with documented acceptable findings). Frankenstein:
  `adapts_to = B2`. It is never set by hand and never before the pilot.
- **The library shows it.** A book's card lists the editions it actually
  has and the levels they reach. Product copy states the rule, not a level:
  "adapted down to the lowest level that keeps the author's meaning".
- **No page promises a level in advance.** Marketing, plan features and
  onboarding may not name B1 (or any level) as something every book gets.
  Fixed in the web client on 2026-09-18 (`almonium-fe b07c669`).
- **Abridged retellings are a different product**, if we ever want them:
  disclosed as retellings, judged on readability and coverage rather than
  fidelity, chosen for books whose content suits it. Not on the roadmap.

## 14. An adaptation's level promises its wording, and the judge is a panel

**Decided 2026-10-05, by the owner.** Section 13 stands: the floor is found
per book and never promised, and nothing is abridged. What changed is who
judges and what the level means.

What we learned, on Frankenstein on 2026-10-04:

- **The September judge could not tell B1 from B2.** Given B1 attempts and
  B2 adaptations of the same chapters, the chapter-analysis model called all
  sixteen B2, although they differ measurably (2.0 to 2.5 percent rare words
  against 4.1 to 5.3). Opus 5.5 and GPT-6.1-sol, asked the same blind
  question, separated them and agreed on 17 of 18 texts. So "five prompt
  versions all judged B2" was evidence about the judge at least as much as
  about the book. None of the judges is validated against human-rated text.
- **A judge wavers at a boundary.** The same judge read the same text B1 once
  and B2 once.
- **Ideas raise a holistic level that no rewording lowers.** The
  confrontation with the creature read B2 for its allusions and sarcasm
  while its sentences were plain.

The rules now:

- **A level on an adaptation promises the wording**: the vocabulary and
  sentence structure. The author's ideas, allusions and irony stay as
  written and do not count toward it. The judges of an adaptation are told
  to rate the wording alone (`ai/chapter_analysis.py`, `WORDING_NOTE`).
- **The judge is a panel** (`DIFFICULTY_JUDGES`): each judge reads the text
  three times and its middle reading counts; the strictest judge decides.
  With no panel configured, a deployed environment keeps the single judge.
- **A chapter read above the target goes back to the adapter once** with
  what the judges cited. The revision stands only if they read it easier.
- **Front and back matter may sit above the target.** Only substantive
  chapters hold a level; an author's introduction is an essay.
- **Fidelity is audited by two auditors from different vendors**
  (`FIDELITY_AUDITORS`). A material finding only one raised holds the gate
  only if the other confirms it. A probe's sampled chapter fails on fidelity
  when more than a tenth of its blocks carry a material finding; every
  finding of a full edition still goes to the editor's queue and holds
  publication there.
- **A whole adaptation is held to what its probe passed at**: the same
  judges read every chapter (`check_adaptation_wording`), and where they
  have read a chapter's current text, theirs is the level its gate uses.

Under these rules the B1 probe of Frankenstein passed on 2026-10-05 (Letter
I, Chapter X after one revision, Chapter XXIII). `adapts_to` still changes
only when a full edition passes both of its gates.

The library's own chapter levels were settled the same day (section 15): the
judges read originals too. Whether the reader should be told which chapters
of an adaptation carry demanding ideas at plain wording is a product
question, open.

## 15. A book is finished without a person, and one judge reads levels

Decided by the owner on 2026-10-05, after a week in which the pipeline grew a
second judge, a second checker and three ways to mend a chapter beside the
ones it had.

- **The pipeline must be able to finish a book with nobody reading it.** The
  owner will prepare books in bulk, in languages they cannot read, and sign
  them off on the judges' and auditors' word, with corrections applied
  automatically and promotion as an explicit switch. Review by a person
  stays possible and is never required: in the automatic flow a review item
  is a note, not a gate.
- **One judge reads levels: the pair.** The level of every chapter, of an
  original as of an adaptation, comes from the configured judges
  (`DIFFICULTY_JUDGES`, on the owner's machine Opus and gpt-6.1-sol
  together, not either alone). gpt-5.6-luna is retired as a judge of
  levels: it read B1 attempts as B2 and disagreed with both stronger models,
  and its estimate beside theirs was the "25 chapters at B2, one chapter
  blocking" mismatch on the B1 Frankenstein.
- **The level of an adaptation is not a ceiling on every chapter.** One
  substantive chapter in ten may sit one level above the target when the
  judges disagree about it (`SPLIT_CHAPTER_SHARE`). The strict ceiling took
  the stricter of two judges on every chapter, so among thirty chapters one
  wavering reading held a sound book: the B1 Frankenstein stood at 27
  chapters B1 and one, its last, read B1 by Opus and B2 by gpt-6.1-sol after
  three rewrites. A chapter both judges read above the target, or one two
  levels above, still holds the book, and so do more disputed chapters than
  the allowance.
- **The production** (`catalog/production.py`) is that pipeline for
  adaptations. It starts the same jobs a person started and asks the same
  gates; it adds no judgement of its own, only an order, limits on how often
  anything is tried, and the rule for corrections: one is written in when
  more than one model stands behind it (both auditors raised it, or the
  other confirmed it), and the chapters it touched are audited again rather
  than taken as read. Translations go through it too, after the levels and
  independent of them: written, read by the two editors, corrected where
  both stand behind a correction, held only by a serious agreed finding that
  could not be placed.
- **Judges read once, and three times only where they disagree.** Of 48
  texts both judges had read three times, their first readings gave the same
  level on 37; Opus never gave two different levels for one text, and
  gpt-6.1-sol did on 11. Stopping at an agreeing first reading would have
  changed one verdict of the 48, from "one judge a level above" to "at the
  target", which the allowance for disputed chapters grants anyway, and
  makes 188 calls where there were 336. Where the first readings differ each
  judge reads twice more and its middle reading counts, as before
  (`pilot_difficulty.panel_readings`). A single configured judge still reads
  `DIFFICULTY_READINGS` times: it has nobody to agree with.
- **A Claude call is costed at the CLI's own price of it**
  (`pricing.plan_priced`), and the CLI's prompt cache is off for these
  requests. The price table undercounted Claude by about 40%: the CLI wrote
  every prompt to a one-hour cache at a premium and a chapter is never read
  back from it. The plan's meter can be read in code after all
  (`claude_meter`, the /usage screen), on a meter every Claude Code session
  of the account shares.
- **A translation review reports serious findings only, and nobody rules.**
  The first review asked two editors for everything they would change, had
  the translator's model write a final wording for each correction and a
  third model (Fable) rule on every disputed and stylistic finding: 1,286
  findings and about USD 7.30 on Frankenstein, against USD 1.08 for the
  translation. The owner: "rest is stylistic noise". The editors now report
  only what misleads or stops a reader; a finding one raised alone goes to
  the other, whose yes confirms it and whose no leaves it for a person
  without a replacement. The final-wording pass and the adjudicator are
  gone, as the adaptation audit never had them.
- **Luna keeps the easy work**: bibliographic metadata, and chapter notes
  (description, recap, themes) where no judges read, which the owner likes
  and which a privately uploaded book should get too.
- **How it is built**: the judges did not become a second pass beside the
  chapter analysis; they became it (`chapter_analysis.edition_spec`). A
  judge answers the same contract the single model did, so the strictest
  judge's reading of a chapter carries its level, its evidence and its
  description and recap, and everything downstream (the book's level, the
  ladder, the adaptation gate, the published projections) reads one source.
  An original is read once per judge, by the whole rubric: its level is a
  label drawn from all its chapters. An adaptation is read three times, for
  its wording: each chapter has to hold the level. Known waste, left for the
  next change of the judges' prompt: every reading writes a recap, and only
  the strictest judge's is used.
- **All three ways to translate stay**: Codex on a plan, Claude Code on a
  plan, and the paid API with gpt-5.6-terra. The plan CLIs are a workaround
  that works on one machine; prices and tools keep changing; the processor
  must be able to run on the paid API alone, at least in principle. Which
  plan translates is a matter of quality for the price at the time.
- **A Claude model is named with its version** in settings and records
  (`claude-opus-5-5`), so a judge cannot change under its own readings.
- **Every answer is held to its schema and a failed call is tried again**
  in the plan CLIs' wrappers, so that one bad answer cannot fail a book.
- **Privately uploaded books** are a second path through the same
  processor: no translation is offered for them (copyright), chapter notes
  are.
- **The marginal notes are written by gpt-6-astra where a plan is there**
  (`GLOSS_WRITER`). On six passages of Frankenstein, three writers under the
  same brief and two other models judging blind: astra was ranked first (75
  of 78 judgements "good", none "wrong"), Opus second (79 of 82, two
  "wrong"), gpt-5.6-terra last by both judges (56 of 62, none wrong, and the
  fewest notes). On the plan astra costs about what terra costs on the API.
  With no wrong note in 39, one writer is enough: no second model checks the
  notes, and a person still approves them before readers see them.
- **Passages the owner rates** (`calibration/level_passages.json`,
  `manage.py judge_passages`): ten passages, the same paragraphs at three
  levels among them, to hold the judges against one person's reading.
- **The writers rank each other** (`manage.py compare_writers`, results
  under `calibration/compare/`). On 2026-10-09, eight passages of Bleak
  House, four writers (Opus 5.5, Fable 5.1, gpt-6.1-sol, gpt-6-astra) and
  the same four judging blind, counting only what the other three said of
  each writer (mean rank of 4, lower is better):
  - Ukrainian translation: astra 2.08, sol 2.29, Opus 2.79, Fable 2.96.
    Both GPT models beat both Claude models in every judge's eyes, the
    Claude judges' included; astra leads sol by a fifth of a rank at
    4.7 times the price ($1.88 against $0.40 for the eight passages).
  - B1 adaptation: Opus 2.54, Fable 2.62, astra 2.88, sol 2.96. Judges
    agreed on the best candidate on 0 to 4 passages of 8, so the order is
    soft; Opus costs 40% of Fable. But the pipeline's own level judges
    (`--read-levels`) read the GPT writers' B1 at B1 on 6 passages of 8
    (both judges), Opus's on 4 and Fable's on 1: the Claude writers
    simplify less, which the ranking rewarded as prose and the level gate
    would send back to be mended. The adapter stays astra; sol lands as
    often at a fifth of the price and is the one to try on a book.
  - Every judge put itself first or second except Fable on translation;
    Fable and astra ranked their own adaptations at 1.38 where the others
    put them at 2.6 and 2.9. A single judge's verdict on its own family
    is not evidence.
  - The same shape as the dictionary entries (`scripts/lexicon_research`
    in the backend, 99 German words): the dearest model is best by a
    small margin, never in proportion to its price. The whole comparison
    cost $22 at list on the plans.
- **The writer never checks its own work.** Every model ranked itself
  about 0.4 of a rank above where the others put it, and the sol judge
  passed sol's own B1 on 7 passages of 8 against astra's 6. A sibling
  may check it, as one of two from different vendors. So since gpt-6.1-sol
  translates (The Time Machine, 2026-10-09: 21 chapters in ten minutes,
  14 agreed corrections, signed off, 2 Codex points), its second editor
  is gpt-6-astra, not sol; that gives back about USD 0.40 of the USD 0.90
  a book that sol saves over astra. Sol as the adapter is on trial on
  Alice's Adventures in Wonderland with the Opus + sol judges, and astra
  reads the result once, blind, as the independent check; if the levels
  hold under astra too, sol adapting is a matter of price (about USD 0.95
  for two levels against USD 1.69), if not, astra stays.
- **Alice (2026-10-10) decided nothing about sol and found a rule instead.**
  Its B1 probe was held on the Caterpillar chapter under both writers: sol
  kept the "Father William" verse word for word, as the protected-block rule
  requires, and the sol judge read the chapter B2 three times on the verse
  alone (Opus read it B1); astra changed the verse and its generation failed
  twice. The sol judge was not soft on sol's own text. A kept verse is the
  original by rule, like front matter, and the level gate has no allowance
  for it; the choice is the owner's: let the judges leave protected verse
  out of a chapter's level, or let a B1 adapter rewrite or cut verse with a
  note. Until then a book with verse in its chapters cannot pass at B1.
  The uk translation by sol was signed off in twelve minutes with 19 agreed
  corrections; the whole production cost USD 0.47.
