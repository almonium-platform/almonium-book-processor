# Night handoff — 18 September 2026

This section supersedes the historical 16 September walkthrough below.

- **B1:** five prompt versions on Preface, IV and X all assessed B2 with the
  existing blind Luna judge. No full B1 edition exists. Do not publish or
  generate a whole book until the calibration and fidelity gates are met.
- **Published locally:** original C1, B2 adaptation, and original-derived
  Ukrainian C1 translation. French human translation remains in review.
- **Authority:** local/staging B1 publication is authorized only after quality
  passes. Production publication and French editorial approval remain Astra's
  decisions. No premium model calls; Terra is the ceiling. Tonight's cap is $10.
- **Checkpoint:** processor `c5f01ed` commits the B1 workflow and prompt v5.
  All processor checks passed (414 tests). Backend, Angular and mobile were
  already committed when this run resumed; verification is running sequentially.
- **Next in progress:** blind judge controls, then a bounded decision on B1;
  cross-client level handling; Ukrainian analysis language and alignment drift.
  This is a work-in-progress checkpoint, not a claim that those tasks passed.

The local B2 reader is
http://localhost:9999/reader/shelley-frankenstein-en-orig-b2 .
The original and Ukrainian companions remain usable independently of B1.

---

# Morning walkthrough — 16 September

Nothing was editorially approved or published overnight. Those decisions are yours.

## Try the new vocabulary flow first

1. Open the [live original reader](http://localhost:9999/reader/shelley-frankenstein-en-orig).
2. Click **Vocabulary** in the bottom bar, then select **11 — CHAPTER V.**
   Expect 21 selected words with actual excerpts: for example, `countenance`,
   and lemma `endeavour` with the observed form `endeavoured`.
3. Click **Look up countenance in Discover**. The lookup carries the excerpt,
   English language and book/chapter context. Discover shows the source and a
   **Back to book** link. Your preferred learner language is not changed.

All 30 original chapters now have current vocabulary data. This reuses the existing
offline lexical stage and pinned spaCy lemmas—no new NLP pass or AI calls. It is a
chapter-filtered selection from the book's useful words, not every chapter word.
The vocabulary chapter selector is independent of your reading position; returning
from Discover opens the book, not a guaranteed chapter jump.

[Real vocabulary screenshot](../../almonium-fe/docs/evidence/reader-20260916/vocabulary-live-original.png)
· [Discover journey screenshot (test fixture)](../../almonium-fe/docs/evidence/reader-20260916/discover-book-context.png).
The live chapter request was verified through the backend; the complete Discover
journey was tested with mocked lookup responses, without a paid live lookup.

### On mobile

Use an updated mobile build: published Frankenstein → reader header's chapter-list
button → **Vocabulary** under **CHAPTER V.** → **Look up countenance**.
Expect the same 21 curated words/excerpts. The existing word sheet shows the book,
chapter and English lookup language even if another learner language is selected.
**Back to vocabulary** returns to the list; dismissing it keeps your reading place.
Missing/old chapter data and offline requests show a message without blocking
reading. The Android export passed, but it does not install the update on a phone.

## Short retrospective and the next slice

- **Done:** full-book offline sentence matching, adaptation difficulty warnings,
  edition-aware web/mobile companions and chapter navigation, and chapter
  vocabulary → source-aware lookup in both clients. No extra NLP stage was added.
- **Verified live:** the published original's vocabulary through the product API
  and Angular; mobile WebView JavaScript in Chromium found all 30 headings,
  jumped to Chapter V and mapped its 21 words to English lookup context.
  Real staff sentence previews were previously spot-checked, not fidelity-approved.
- **Fixture/unit evidence only:** public B2/original/Ukrainian reader combinations,
  the full Angular Discover journey, mobile vocabulary states/context helpers and
  companion-layout browser checks. The mobile tests do not mount native sheets;
  no live generated-definition lookup or save-card round-trip was performed here.
- **Needs you:** B2 fidelity review/editorial level, separate B2 and Ukrainian
  publication, the companion-default decision, and native-device acceptance.
  Device checks must cover sheet transitions, selection, dark/pressed states,
  real airplane-mode behavior and saving a looked-up word. Source attribution is
  preserved during lookup; persistent book/chapter links on saved cards are not
  implemented by this slice.

**My single next-slice recommendation after the reset:** a device-backed
read → chapter vocabulary → lookup → save word → resume-reading acceptance pass,
fixing the concrete problems it reveals. Start with the already-published original;
include real B2/Ukrainian companions only after your release decisions. This closes
the largest remaining user-facing verification gap. Defer clause alignment and
new generation work until this loop is proven on a phone.

## Then review B2, if you want to release it

1. Open the [B2 edition](http://localhost:8000/editions/f0617488-6553-4131-9a13-2e470a62ffa9/).
   Expect target B2 and all 30 chapters estimated B2. Two fidelity-related review
   items remain open. “Level pending” in a companion label means the editorial
   level has not been confirmed, not that analysis is missing.
   Front matter means introductory extras; back matter means
   end extras. These remain readable but are excluded from the overall difficulty
   estimate. Storytelling letters/prologues belong to the main content.
2. Open [B2 ↔ original, Chapter V](http://localhost:8000/editions/f0617488-6553-4131-9a13-2e470a62ffa9/sentence-preview/da3a845f-572c-4ed3-acf3-3172bbc972f9/?chapter=11).
   Click marked sentences; genuine splits highlight several sentences together.
   Use the chapter picker to compare other chapters. All 815 blocks were processed
   locally, without paid alignment calls. Uncertain passages remain paragraph-only.
3. Compare [B2 ↔ Ukrainian](http://localhost:8000/editions/f0617488-6553-4131-9a13-2e470a62ffa9/sentence-preview/5a0a2c21-0350-4500-aaae-98a634fccafe/?chapter=11).
   This translation derives from the original, not from B2. The wording may be more
   literary; correspondence is computed directly for this pair, not composed.
4. **Your decision:** inspect fidelity, resolve the fidelity review items only if
   satisfied, set/confirm editorial B2, and complete review. Passing the automated
   difficulty gate is not fidelity approval.
5. **Your decision:** publish the original/companion editions you want available,
   then the adaptation. The Ukrainian edition must be independently approved and
   published before it can appear as a public companion. Use the processor's
   publication buttons, not database edits. Nothing here requests automatic release.
6. The [live Angular original](http://localhost:9999/reader/shelley-frankenstein-en-orig)
   is available now. After you publish B2, open
   [the B2 reader](http://localhost:9999/reader/shelley-frankenstein-en-orig-b2).
   Choose a companion and try Side by side, Inline and On demand. Marked sentences
   highlight their counterparts; selecting text still takes priority.
7. Mobile: open the published book, then reader settings → Companion edition.
   Choices include language, level and edition type. Try Inline and On demand.
   Mobile builds and browser-script tests passed; a physical-device check is still
   needed. Public B2/UK reader flows cannot be verified live until you publish them.
   The new chapter-list button in the reader header jumps through local headings;
   complete level estimates/descriptions appear when the backend supplies them.
   Failed enrichment never prevents navigation. This requires the updated mobile
   bundle; an Android export does not install it on your device.

## Your remaining decisions

- Fidelity approval and editorial B2: review the two open fidelity items yourself.
  Neither a passing B2 judge nor working highlights approves fidelity.
- Publication: choose when to release B2 and Ukrainian separately. The processor
  now names an unpublished source as a prerequisite instead of queueing a doomed
  hand-off. No editions were released during this work.
- Companion default: both clients currently **include translations of other
  editions by default**, with an explicit On/Off switch in companion selection.
  They say “based on another edition, not this adaptation.” Turning this off while
  reading such a companion returns to single-edition reading. Please decide
  whether this default feels useful; it does not claim the Ukrainian is B2.

## Evidence and what it proves

Angular production-bundle browser tests cover B2 ↔ original and B2 ↔ Ukrainian
in all three modes, including highlighting, chapter navigation and switching off
original-derived translations. **These public-reader pairs use test fixtures**, not
unpublished content exposed through a public endpoint.

| Mode | B2 ↔ original | B2 ↔ Ukrainian | Companion switch |
| --- | --- | --- | --- |
| Side by side | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-EN-side.png) | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-UK-side.png) | [On](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-side-on.png) / [Off](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-side-off.png) |
| Inline | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-EN-inline.png) | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-UK-inline.png) | [On](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-inline-on.png) / [Off](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-inline-off.png) |
| On demand | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-EN-overlay.png) | [Image](../../almonium-fe/docs/evidence/reader-20260916/parallel-UK-overlay.png) | [On](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-overlay-on.png) / [Off](../../almonium-fe/docs/evidence/reader-20260916/companion-switch-overlay-off.png) |

Real processor data was rendered in a database **read-only transaction**, with
an unsaved test staff principal—not your account or browser session. Screenshots:
[edition detail](evidence/reader-20260916/detail.png),
[paragraph comparison](evidence/reader-20260916/reader-original.png),
[Ukrainian paragraph comparison](evidence/reader-20260916/reader-uk.png),
[original sentence preview](evidence/reader-20260916/sentences-original-11.png),
[Ukrainian sentence preview](evidence/reader-20260916/sentences-uk-11.png).
This verifies rendering and interactions, not staff login or publication.
[Live Angular original](evidence/reader-20260916/angular-live-original.png) uses
the actual public backend. Its 30-entry contents list now scrolls instead of
clipping chapter estimates/descriptions; a
[full chapter-list regression](../../almonium-fe/docs/evidence/reader-20260916/chapter-navigation.png)
also checks this.

Real sentence highlights were clicked in chapters 1, 10, 11, 20 and 30 for both
pairs. The samples preserve simpler English alongside more literary original/UK
wording; chapter 30 correctly highlights two adapted sentences against one
Ukrainian sentence. This is a spot check, not whole-book fidelity approval.
One source typography issue worth inspecting: chapter 30 starts “M y present
situation”; the adaptation has “My present situation”. No source text was edited.

## Local services and evidence

Backend startup is detached, using the `local` profile on port 9998, with bounded
JVM heaps. Log: `/tmp/almonium-be.log`. Processor: port 8000; existing Angular dev
server: port 9999. Heavy checks run sequentially to avoid memory pressure.

Processor web/worker were rebuilt/restarted successfully. Processor health and
the backend's public original-book endpoint both return 200. No temporary browser
test server is intentionally left running; the existing Angular dev server was
left alone. No paid AI calls were needed.

Vocabulary checks: processor 334 tests plus Ruff/format/migrations/system checks;
backend Spotless, nine focused tests and full Maven verify; Angular lint, 274 tests,
production build and eight browser cases. Mobile: TypeScript, 103 tests, ESLint
(one existing generated-file warning), Android export and the read-only live
WebView check passed sequentially via direct Node commands. Native-device
acceptance remains pending. Reproduce the bridge check with
`node scripts/check-reader-vocabulary.mjs` in the mobile repository.

Vocabulary implementation commits:

- Processor `07b0402`: current, source-attested chapter vocabulary contract.
- Backend `331707ea`: typed public chapter-vocabulary endpoint.
- Angular `e2767be`: vocabulary panel and source-context Discover links.
- Mobile `8387875`: chapter vocabulary and source-aware in-reader lookup.

See `PRODUCT_READER_DELIVERY.md` for implemented slices, verification and remaining
work. The real public B2/Ukrainian acceptance flow still waits for your release
decisions; no release or editorial state was changed in the mobile slice.
