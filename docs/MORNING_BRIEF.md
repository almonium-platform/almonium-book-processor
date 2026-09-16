# Morning walkthrough — 16 September

Nothing was editorially approved or published overnight. Those decisions are yours.

1. Open the [B2 edition](http://localhost:8000/editions/f0617488-6553-4131-9a13-2e470a62ffa9/).
   Expect target B2 and all 30 chapters estimated B2. Two fidelity-related review
   items remain open. Front matter means introductory extras; back matter means
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

## Local services and evidence

Backend startup is detached, using the `local` profile on port 9998, with bounded
JVM heaps. Log: `/tmp/almonium-be.log`. Processor: port 8000; existing Angular dev
server: port 9999. Heavy checks run sequentially to avoid memory pressure.

See `PRODUCT_READER_DELIVERY.md` for implemented slices, verification and remaining
work. This brief will be updated with findings from the current walkthrough.
