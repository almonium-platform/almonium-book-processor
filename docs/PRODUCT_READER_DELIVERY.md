# Processor → backend → web → mobile delivery

Updated 2026-09-16. This is the next visible product work, not a calibration project.

Status 2026-09-18: the B2 adaptation and the Ukrainian translation are
published in the source environment and reach staging and production by
promotion ([PROMOTION.md](PROMOTION.md)); the published B2's fidelity findings
were applied ([BACKLOG.md](BACKLOG.md)). Of the slices below, owner-only
editorial release and native-device acceptance are the open ones.

## Morning handoff update

Start with [the 2026-09-18 brief](evidence/morning-brief-20260918.md): click
order, screenshots and the owner's decisions (fidelity, publication, companion default). No fidelity warnings
were approved and no edition was published during this work.

- Publication now requires the source edition to be published first, matching
  the backend prerequisite. Publishing one edition never silently releases its
  companions. Existing current sentence correspondences become readable when
  both editions are public.
- Staff comparison labels distinguish same-language editions and explain the
  difference between inherited paragraph groups, estimated sentence matches and
  editorial fidelity.
- Both clients offer indirect translations by default with clear lineage and
  an explicit switch to hide them. Angular chapter/companion menus no longer
  overlap. Six production-bundle browser cases cover both pairs in all modes;
  a seventh checks that 30 enriched chapter entries scroll without being clipped.
  The real original's desktop contents list was checked after this fix too.
- Mobile now has local chapter navigation plus optional current CEFR/descriptions
  from the product chapter endpoint. A missing enrichment request never blocks
  reading or navigation. Live original: all 30 headings and Chapter V enrichment
  checked in browser execution of the WebView bridge; Android export passes.
- Processor web/worker were rebuilt, and the detached backend remains available.
  Heavy builds/browser runs were sequential. No paid calls were needed.
- Chapter vocabulary now reaches Angular through the typed backend endpoint.
  Existing lexical artifacts retain source-attested examples with pinned-model
  lemmas; no separate NLP stage was added. All 30 published-original chapters
  were refreshed without text edits, review changes or publication. The reader's
  Vocabulary panel links to Discover with language, excerpt and book/chapter context.
  See the morning brief for live clicks and screenshots. Backend full verify and
  Angular lint/274 tests/production build/eight browser cases pass.

### Next slices

1. **Owner-only editorial release**, then the actual public B2/original/Ukrainian
   round-trip. Fixture browser tests and read-only staff snapshots do not replace
   this acceptance test; do not publish or dismiss warnings on the owner's behalf.
2. **Native-device acceptance** of chapter navigation, companion switching,
   selection, paper/night modes and offline reading. Builds and browser-script
   tests cannot certify native UI behavior.
3. **Chapter vocabulary — implemented across processor/backend/web/mobile.** Mobile
   chapter navigation now opens curated source examples and passes book/chapter
   context plus source language to its existing lookup sheet. Missing/stale/offline
   requests preserve reading. Mobile commit `8387875`: TypeScript, 103 tests,
   ESLint, Android export and read-only live WebView check pass. Native sheet and
   lookup/save/resume acceptance is the recommended next bounded slice; persistent
   source links on saved cards and whole-library IR remain separate work.
4. **Clause-level alignment** only where sentence groups are too broad. Keep the
   existing safe paragraph fallback and exact-pair provenance; no paid alignment
   needed for the current sentence feature.

## Current boundary

The processor owns source text, editions, chapter review, adaptation targets and
versioned analysis. Spring owns product access and publication projection. Angular
and Expo consume the product API, not Python internals or staff endpoints.

Backend and Angular already select a companion by edition slug and render
same-language pairs plus optional many-to-many sentence highlights. The reader
contract and mocked browser interaction were tested in the preceding delivery;
that is not a completed live processor → backend → browser publication test.

Mobile now selects a companion by edition slug, labels level/type, and consumes
the same product parallel-edition endpoint. Its WebView uses `data-side` and
supports grouped sentence highlights in inline/on-demand modes. Native-device
verification remains outstanding; optional chapter enrichment is implemented.
Firebase bearer authentication must remain separate from Angular session cookies.

## Next sessions, in order

1. **Reviewed chapter into edition — implemented.** A completed, currently assessed
   whole-chapter pilot can be applied to its unpublished B2 adaptation. The staff
   preview supplies a target revision token and requires fidelity notes. Exact
   source and target block/group identity are checked; old text is retained in
   ContentBlockRevision. Reapplication does not duplicate text changes. The edition
   returns to review; sentences, lexical/QA and difficulty refresh in workers.
   Unchanged chapter-analysis windows are reused. No whole-book regeneration.
2. **Finish content review and perform the local publication round-trip.** Resolve
   remaining actionable QA and record edition review. Confirm
   editorial B2 only after the current assessment and review. Start the backend
   with its documented local profile; publish through the signed worker hand-off.
   In Angular, open adaptation ↔ original and adaptation ↔ Ukrainian. Verify real
   catalogue selection, truthful labels, all block pairs, and unavailable-pair
   handling. Do not bypass publication gates to make an integration test pass.
3. **Chapter data in backend and Angular — first slice implemented.** Public
   `/editions/{slug}/chapters/` feeds product `/public/books/{slug}/chapters`.
   Stable chapter UUID/order/title, analysis status, complete current CEFR estimate
   and ordered spoiler-free descriptions appear in Angular's chapter navigation.
   Missing enrichment never blocks reading. Review/private editions return 404;
   stale or incomplete estimates are not displayed. Editorial book level remains
   separate. Angular and mobile vocabulary are now implemented in the follow-up
   above; reader-facing provenance detail and individual chapter SEO routes remain
   next. No recaps in defaults.
   Verification: 313 processor tests; focused backend content tests; 24 Angular
   reader/contract tests, development build and mocked browser test pass. Processor
   rebuilt/restarted; live original chapter endpoint returns 30 chapters. Backend
   and Angular changes are not yet a live publication round-trip. Some generated
   descriptions hint at later events despite the prompt's spoiler-free intent;
   review these before treating them as finished public SEO copy.
4. **Offline sentence correspondence — implemented and run on both full pairs.**
   Paragraph groups bound monotonic 1:1, 1:2, 2:1, 2:2, 1:3 and 3:1 matching.
   Prefer smaller matches; uncertain, oversized or encoder-truncated inputs keep
   paragraph fallback. Artifacts include both current texts/segmentations and the
   configured model/algorithm identity. Staff preview queues a tracked, cached
   whole-pair worker job, with chapter selection and progress. No paid calls.
   `offline-sentence-v2`: B2 ↔ original run
   `1e5cd966-bd85-46f6-a9b7-19993a1a749d`: 815 blocks, 3296 highlightable groups,
   6 entirely paragraph-only blocks. B2 ↔ Ukrainian run
   `ba22bf2d-fc0a-499a-887d-44f999022148`: 815 blocks, 2190 groups, 49 paragraph-only
   blocks. Samples from chapters 1, 10, 11, 20 and 30 preserve ordinary 1:1 matches
   and genuine sentence splits. These counts are not calibrated accuracy claims.
   Clause/phrase alignment and wider quality review remain separate future work.
5. **Expo parity against that same contract.** Extend authenticated book info and
   companion selection to edition identity; label language + level + edition type.
   Replace language-based WebView side detection with `data-side`. Add tap-based
   confirmed sentence highlighting without interfering with word selection.
   Keep query/offline cache identity owner-, edition- and companion-specific; test
   same-language pairs, failed companion requests, offline base reading and dark
   mode. Run mobile `npm run check` and an Expo export/development build; do not
   claim on-device verification from web tests.

Useful starting points:

- Processor: `catalog/pilot_application.py`, `catalog/parallel_content.py`,
  `catalog/publication.py`, `docs/PARALLEL_READING_NEXT.md`.
- Backend: `docs/PROCESSOR_READER_CONTRACT.md`, `learning/book/controller/BookController`,
  `learning/book/controller/open/BookOpenController`.
- Angular: `docs/PROCESSOR_READER.md`, `e2e/processor-parallel.spec.ts`.
- Expo: `src/types.ts`, `src/api.ts`, `app/book/[bookId].tsx`,
  `app/reader/[bookId].tsx`.

Keep verified commits separate per repository. Existing unrelated notification
and settings changes in the backend/frontend worktrees belong to other work.

## Where to test locally

- Live Angular original: `http://localhost:9999/reader/shelley-frankenstein-en-orig`.
  Verified against the live backend: 30 estimates and 32 window descriptions.
- Staff B2 ↔ original sentence preview:
  `http://localhost:8000/editions/f0617488-6553-4131-9a13-2e470a62ffa9/sentence-preview/da3a845f-572c-4ed3-acf3-3172bbc972f9/?chapter=11`.
- For Ukrainian, replace the companion UUID with
  `5a0a2c21-0350-4500-aaae-98a634fccafe`. Staff sign-in is required. These previews
  do not publish the editions or clear outstanding fidelity review warnings.

Verification: processor 319 tests and canonical checks pass. Mobile TypeScript,
91 tests, ESLint (one existing generated `.expo` warning), Android export and
browser execution of inline/on-demand WebView scripts pass. The `npm run check`
wrapper fails with the environment's `Exec format error` bin shims; equivalent
underlying commands were invoked via Node. No new dependency or auth changes.

## Follow-through: difficulty gate and reader parity

Current chapter projections now maintain a tracked `adaptation_difficulty_gate`
review warning. A manual resolve cannot dismiss a currently failing gate. The
worker clears this warning after a current passing reassessment; other fidelity
warnings and editorial approval remain untouched. A test covers a B2 book whose
excluded front-matter chapter is C1: publication/review remains blocked despite
the aggregate B2 label.

Angular now highlights marked groups in side, inline and overlay modes, with text
selection taking precedence. Spring validates both sides' offsets and complete,
nonduplicated sentence indexes before rendering clickable spans; an invalid pair
falls back to plain paragraph text on both sides instead of leaving orphan links.

Follow-through verification: 320 processor tests and all canonical checks pass;
24 Angular reader/contract tests, development build and browser tests in all three
parallel modes pass; Spring's six focused content-service tests pass. Processor
web/worker were rebuilt/restarted, and the backend was restarted on local port
9998 with the `local` profile. The live original chapter endpoint returns 200.
Refreshing the B2 edition's saved projections (no AI calls) confirms no difficulty
blocker; only `adaptation_chapter_replaced` and `adaptation_fidelity_review` remain
open. Full public B2/UK publication and native-device acceptance are still pending.

## Local content update

Pilot `da64bf26-f698-4c8d-b1ce-af83934eda8c` has been applied to Chapter IV of
`shelley-frankenstein-en-orig-b2`: 13 block changes with original IDs/groups retained.
Two subsequent audited editorial corrections resolve the documented wording
concerns (`kept` → `chosen`, `hopes` → `tries`). No other chapter or source-original
text changed. The edition remains in review, with no editorial CEFR or publication
approval silently assigned. Backend, Angular and mobile code were not changed in
this chapter-application iteration.

The final reassessment after both corrections is complete: **30/30 chapters B2,
aggregate B2**. The original's computed/editorial C1 remains unchanged. The target
difficulty gate passes; the two edition-review warnings still require resolution.
