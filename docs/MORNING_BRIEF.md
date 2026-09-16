# Morning walkthrough — 16 September

Nothing was editorially approved or published overnight. Those decisions are yours.

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

Checks: processor 321 tests plus Ruff/format/migrations/system checks; Angular
lint, 267 tests, production build and seven browser cases; mobile TypeScript,
96 tests, ESLint (one generated-file warning) and Android export. The mobile
`npm run check` executable shim fails in this checkout; equivalent underlying
checks ran via Node. No native-device acceptance is claimed.

Implementation commits:

- Processor `c716f0f`: source-publication prerequisite, clearer staff comparison.
- Angular `96f050a`: companion provenance/filter; `9c63311`: screenshot capture;
  `4d999a1`: mutually exclusive menus; `fa55299`: current integration notes;
  `fa133b7`: unclipped full-book chapter navigation.
- Mobile `4772728`: companion provenance/filter; `4b0c3e2`: chapter navigation,
  optional estimates/descriptions and truthful reading-mode labels.

See `PRODUCT_READER_DELIVERY.md` for implemented slices, verification and remaining
work. This brief will be updated with findings from the current walkthrough.
