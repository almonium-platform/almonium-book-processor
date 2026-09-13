# Pipeline review and delivery plan

Date: 2026-09-13. Review of `ALMONIUM_PIPELINE_DECISIONS.md` against this
checkout and the frontend product vision. Claude's original document is
preserved; use this review and its delivery tickets to qualify its proposals.
These are engineering recommendations, not approval of new pricing or quotas.

## Direction and corrections

The service boundary is right: Python prepares versioned editions and artifacts;
the product backend owns access, subscriptions, learner state and delivery;
Angular/Expo own reading. Chapter analysis, generated parallel editions and
book-sourced Discover examples fit the product vision particularly well.

1. **Normalization is not modernization.** Normalization extracts faithful,
   readable structure; audited corrections repair source defects. Modernization
   creates a separate edition that changes historical language. Neither age nor
   a C2 estimate makes an original useless. Keep the original available.
2. **Separate generation lineage from alignment identity.** A generated edition
   has one immediate source and an exact source revision. Independently imported
   human translations need not claim an imported original as their actual
   generation parent. Sibling B1/B2 adaptations should normally use the same
   approved source, avoiding B2→B1 generation drift. A reviewed modernization
   may be that source, but its mere existence must not silently change the
   source of a new adaptation. Preserve canonical block groups through the tree;
   namespace correspondence by its canonical edition/revision. “Distance from
   the author” is not a measurable or enforceable invariant.
3. **Modernization needs examples and judgment.** Use edition language and
   actual obsolete usage, not universal 1800/1900 cutoffs. Work publication year
   may be centuries older than the wording of a translation. Store evidence
   spans and a rubric-based archaism rating; an LLM's scalar is not a measured
   token percentage. Preserve setting, characterization and intentional style.
4. **B1/B2 are a sensible pilot, not schema limits.** C1 can help with a difficult
   source. C2→B1 may be feasible for some books; A2 is not inherently a summary.
   Judge fidelity and usefulness before offering it. Abridgement removes selected
   content and records omissions; a retelling also rewrites/condenses it. The
   150k-word trigger and whole-scene-only rule are editorial options, not laws.
5. **LLM-first difficulty is reasonable; calibration still matters.** CEFR
   describes learner activities, so a book badge is an estimated reading demand,
   not a certified property of the text. Retain editorial `cefr_level` separately.
   Self-reported confidence is not an 80% probability of correctness. Keep a
   small multilingual human-rated set to catch systematic model/prompt drift.
   Existing wordfreq bands are frequency bands, not CEFR bands: there is no
   deterministic “two CEFR bands apart” referee until separately validated.
6. **Analyze whole chapters within explicit limits.** Combine difficulty,
   evidence, archaism, characters/themes and summaries in a bounded structured
   request, but persist separately versioned artifacts so a summary update does
   not replace difficulty. Long chapters need complete, block-bounded windows,
   overlap deduplication and aggregation; record coverage and never label a
   sample as full analysis. Bound output and record real cost, retries and
   latency; “under a dollar” is not an invariant. Treat book text as untrusted
   input, never as instructions to the model.
7. **Compute corpus facts from the corpus.** First encounter requires ordered
   occurrences across the edition, not a single chapter prompt. Hard words must
   be verified against source spans. A chapter-relative “above its band” filter
   misses useful B2 words in a C1 chapter: store candidates and personalize later.
   Keep spoiler-free descriptions separate from recaps, and hide spoilers by
   default. Content notices are suggested evidence-bearing annotations, not a
   guarantee of age suitability. Quizzes can be optional, per edition/revision,
   with answer evidence; they need not block the first analysis release.
8. **Aggregation is a versioned heuristic.** Start with a nearest-rank 75th
   percentile over substantive chapters, excluding explicit front/back matter;
   show min/max, chapter distribution and analysis coverage. Record token counts
   and a token-weighted comparison to expose segmentation sensitivity. Do not
   average confidence and call it book accuracy. Missing chapters mean a partial
   estimate. Editorial confirmation remains explicit.
9. **Do not force changes to already-suitable chapters.** Assess all chapters,
   allow unchanged blocks/chapters to be copied exactly, and run a consistency
   review across the resulting edition. Generation may return unchanged text.
   Record copied/changed provenance and re-estimate the output: requested B2 is
   not demonstrated B2. A changed-block ratio is a diagnostic, not proof of
   fidelity. Preserve block correspondence while allowing sentence splits;
   strict sentence-count preservation conflicts with syntax simplification.
10. **Original reveal is useful; full comparison is an experiment.** Start with
    a paragraph reveal that distinguishes immediate source from original ancestor.
    There is no basis here for “same-language comparison has no pedagogical
    value” or a claim that nobody else offers it. Measure usage before investing
    in another sustained reading mode. Do not infer learner improvement merely
    from reading an adaptation.
11. **SEO belongs on the product site.** Use stable edition/chapter URLs with
    server rendering or prerendering, useful descriptions, canonical links,
    sitemaps and appropriate language alternates. Index approved public content
    only; exclude private imports and reading-state/pair permutations. A default
    single-language chapter plus optional parallel view avoids a URL explosion.
    More pages alone do not guarantee traffic. Angular can rank; Google renders
    JavaScript, while recommending server rendering/prerendering for robustness.
12. **Discover is retrieval, but need not start with a vector service.** Export
    versioned lemma occurrences from the worker; serve/rank in the backend,
    where ownership and current reading state are known. Index language, lemma
    and POS, retaining surface forms, sentence/block revisions and offsets.
    Rank same-sense usable examples from current reading, then owned library,
    then approved public catalogue. Polysemy needs disambiguation or reranking;
    exact lemma matching alone cannot distinguish river bank from financial bank.
    Prefer short context with limited unknown vocabulary without pretending to
    know the CEFR of every word. Private examples stay owner-scoped and never
    enter shared caches. Deletion/withdrawal removes their serving projection.
13. **Private imports need an explicit product policy.** Reuse secure ingestion
    and available analysis, with owner authorization on every result and retry.
    Keep three imports/month as the working launch proposal rather than silently
    replacing it with ten slots. Rate, bytes/tokens, concurrency, storage and AI
    spend are different limits; a storage-only cap permits costly delete/reimport
    loops. Start with reading and analysis. Leave private derivatives behind
    entitlement, rights and budget policy; user-owned or licensed material must
    not be equated with unauthorized copyrighted material. Choose one bridge
    language per requested translation from supported fluent languages initially;
    fluent-language slots must not imply unlimited full-book generation. The
    precise quota and eligibility remain product decisions, not implemented here.
    A public-library request sends metadata only and requires separate rights
    review; it must never promote private text automatically.
14. **Capabilities are independent and evaluated.** Keep the broad language enum
    and basic manual cards; resolve feature availability by language/provider,
    model version, measured quality and operational availability. Public books
    being absent says nothing about languages users may import. Missing NLP can
    make enrichment unavailable without invalidating faithful reading, but never
    disguise a blank spaCy model as successful analysis. An explicit tested
    sentence-only fallback differs from invented lemmas. LLM support is neither
    universal nor equally reliable. Show understandable availability, rather
    than silently removing a feature the learner was promised.
15. **Phrase alignment is not already solved by block groups.** First establish
    N:M sentence correspondence inside matching blocks; equal sentence counts
    alone prove nothing. Evaluate SimAlign/awesome-align on actual language pairs
    and idioms, then decide offline, LLM or hybrid. Dependency subtrees are a
    heuristic, not a definition of equivalent phrases. Allow discontinuous and
    unaligned spans. Cache by both text revisions/hashes, sentence segmentation,
    aligner/model/prompt version, language pair and direction; never forever by
    sentence ID alone. Specify half-open Unicode code-point offsets and convert
    explicitly to JavaScript UTF-16, with emoji/combining-character tests.

## Verified code findings

- `catalog/tasks.py:publish_edition` already refuses a missing CEFR level. Nullable
  drafts versus a required publication field are intentional, not a demonstrated
  null-publication bug. There is no computed estimate producer yet; saying it
  already shares the editorial column is inaccurate.
- Backend `BookPublicationService.publish` does overwrite `cefrLevel` from the
  processor. Choose an editorial authority before adding competing overrides.
  Recommended: processor staff own edition level, backend projects it. If backend
  overrides are required, add a distinct override field and precedence rules.
- Translation register was parsed from the editable translator credit and silently
  fell back to contemporary neutral. Ticket P0-1 below fixes that locally.
- `processing/nlp.py` currently permits a blank sentence-only pipeline, whereas
  lexical analysis has stricter model requirements. Therefore “all NLP refuses
  blank pipelines” overstates the current implementation. P4-1 must expose the
  actual sentence provider/quality in run provenance and distinguish missing
  configured models from intentionally supported fallback capabilities.
- Generated block IDs establish structural correspondence, not translation
  correctness. Zero structural warnings and model confidence do not eliminate
  semantic review; the first shelf still needs human spot checks, followed by
  the revision-aware reporting workflow in P4-3.
- The older pipeline document's CLI-only architecture and unconditional cheap
  deterministic preference no longer describe the current Django service/user
  preference. Its separate-artifact, faithful-source and privacy rules remain
  useful. The historical backlog also lists completed translation work as pending.
- This review covers the supplied decision document and repository context, not
  unseen Claude Design mockups. The claim that no public reader exists has not
  been verified against a running deployment.

## Delivery tickets

Use these IDs to start future sessions. Each ticket includes implementation,
offline regression tests, canonical checks and focused commits in each affected
repository. Read that repository's guide first. Public contract work must cover
both Angular and Expo. Do not build the public reader in the processor.

| ID | Repository / dependency | Work and acceptance criteria |
|---|---|---|
| P0-1 | processor | Dedicated literary register, conservative legacy backfill, retry independent of translator credit, unknown register fails before paid work. Implemented in this change. |
| P0-2 | processor + backend | Define source-of-truth and versioned publication contract for editorial/computed level, chapter metadata, lineage, register, generated/reviewed labels and rights. Old consumers remain compatible; retries do not erase overrides or publish stale content. |
| P0-3 | processor | Add language-mismatch and chapter-size warnings with front-matter/verse exceptions; calibrated fixtures and staff resolution. Enrichment failure must not take a readable original offline. |
| P1-1 | processor; P0-1 | Implemented: bounded chapter-analysis schema, prompt, provider adapter, Celery task and staff trigger. Per-chapter hashes include actual text, language, rubric and provider versions; resumable jobs account each attempt and reject stale completion. Fake-provider tests cover failures and privacy. See [operation and limits](CHAPTER_ANALYSIS.md). |
| P1-2 | processor; P1-1 | Store separate current difficulty/summary artifacts and chapter projections, partial coverage, percentile distribution, evidence and editorial override. Source edits invalidate affected analysis. UI shows pending/partial/stale/failed distinctly. |
| P1-3 | processor; P1-2 | Evaluate a small human-rated EN/DE/UK sample including letters, dialogue, archaic and modern prose. Record model disagreement, coverage and actual cost. First-encounter vocabulary comes from ordered source occurrences. |
| P2-1 | processor; P1-2 | Explicit modernization source selection, lineage/revision and block-group integrity. Generate one reviewed pilot; preserve source, setting and authorial content. No automatic year threshold. |
| P2-2 | processor; P1-3 | Generate one B2 adaptation from an approved source, retain suitable text, allow sentence splits, persist transformation decisions, validate completeness/fidelity and reassess difficulty. Original remains publishable independently. Add B1 after pilot review. |
| P2-3 | backend + clients; P0-2, P2-2 | Group editions by work, offer useful level choices and original/source reveal, disclose generation and actual review status. Test missing ancestors, withdrawn editions and same-language pairs. |
| P3-1 | backend + web; P0-2 | Ship one approved public chapter with crawlable HTML, stable URLs, metadata, neighboring chapters and optional parallel text. Verify unauthenticated access, canonical behavior and private isolation. Can proceed alongside chapter analysis. |
| P3-2 | processor + backend; P1-2 | Publish versioned lemma occurrence projection and example lookup; source spans round-trip, POS/sense ambiguity is handled, owner filters precede ranking, withdrawal/deletion clears serving data. Start with PostgreSQL indexes. |
| P3-3 | clients + backend; P3-2 | Discover shows examples, prioritizes current reading and deep-links to the exact passage. Test homographs, missing books, private examples and changing text revisions. |
| P4-1 | backend + processor + clients | Define per-feature language capabilities and explicit unsupported-enrichment states; preserve manual cards. Test one supported and one unsupported NLP language, including private imports. No silent blank-model fallback. |
| P4-2 | backend + processor + clients | Implement private-import quota accounting, size/concurrency/AI budgets, idempotent retries and deletion retention. Keep derivative generation disabled until rights/entitlement policy is settled. Verify no cross-owner reads, callbacks, artifacts or cache hits. |
| P4-3 | processor + backend + clients | Wire UserErrorReport to exact edition/block revision, deduplicated staff triage and audited correction; invalidate dependent artifacts and republish corrected versions. Include reporter authorization and rate limits. |
| P5-1 | processor + backend + clients; P2-3 | Evaluate N:M sentence then phrase alignment on demanded pairs; versioned bounded jobs, discontinuous spans, uncertainty fallback and Unicode-safe rendering. No all-pairs catalogue generation. |
| P5-2 | processor + infra | Audited source/media retention, derivative invalidation, operational budgets and production routing; coordinated separate infra commit. Audio and quizzes remain optional follow-on pilots. |

Suggested next session: P1-2 (chapter/book projections and separate artifacts). In parallel product planning,
P0-2 then P3-1 delivers the first public reading surface without waiting for
adaptation, phrase coloring or every enrichment.

## External references checked for this review

- [Council of Europe CEFR descriptors](https://www.coe.int/en/web/common-european-framework-reference-languages/cefr-descriptors): the basis is learner proficiency descriptors, not a ready-made text classifier.
- [Google JavaScript SEO](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics): JavaScript rendering is supported; server rendering/prerendering remains recommended.
- [US Copyright Office](https://www.copyright.gov/what-is-copyright/): derivative rights, permissions and exceptions require distinctions. This does not establish a global legal rule for private imports; deployment-specific review is still needed.
- [SimAlign paper](https://aclanthology.org/2020.findings-emnlp.147/): evidence for an offline word-alignment candidate, not proof of universal phrase correspondence.
