# Processor → backend → web → mobile delivery

Updated 2026-09-15. This is the next visible product work, not a calibration project.

## Current boundary

The processor owns source text, editions, chapter review, adaptation targets and
versioned analysis. Spring owns product access and publication projection. Angular
and Expo consume the product API, not Python internals or staff endpoints.

Backend and Angular already select a companion by edition slug and render
same-language pairs plus optional many-to-many sentence highlights. The reader
contract and mocked browser interaction were tested in the preceding delivery;
that is not a completed live processor → backend → browser publication test.

Mobile still uses `{id, language}` variants and `/books/{id}/parallel/{language}`.
Its WebView identifies secondary spans by language, so it cannot reliably offer
original English alongside simplified English. Do not call mobile caught up yet.
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
3. **Chapter data in backend and Angular.** Define one explicit public chapter DTO
   carrying stable chapter identity/order/title, spoiler-free description, current
   estimated CEFR with coverage/provenance, and useful vocabulary when available.
   Keep editorial level and requested adaptation target distinct. Project through
   the product API; add actual chapter navigation and level/vocabulary panels.
   Private chapters must never enter public routes. No recap spoilers in defaults.
4. **Offline sentence correspondence in the existing reader.** Use the existing
   paragraph groups as bounded windows; persist N:M sentence spans keyed by both
   current texts and segmentations. Same-language and translated pairs need their
   own correspondence. Preserve paragraph fallback. No further paid alignment by
   default; clause/phrase highlighting follows reliable sentence coverage.
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
