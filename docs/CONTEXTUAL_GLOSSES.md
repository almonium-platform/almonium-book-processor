# Contextual glosses

Staff can open **Contextual glosses** on a public edition, choose a chapter,
generate paid note candidates, edit their wording, and approve or reject them.
They can also write a draft without an AI call. Generation uses the edition's
quality model in chapter windows and records the prompt, model, response, usage,
cost and failures in the normal AI ledger. A successful request is idempotent
for its source text, processor version, prompt version and model.

The model supplies an exact short quote and block ID. The worker accepts a
candidate only when that quote occurs exactly once in the block and stays in
one sentence. Notes contain same-language explanations, not translated text.
All AI candidates begin as drafts; staff approval is required to publish them.
Approval rejects overlapping notes. A changed source block invalidates its
existing anchors automatically, including already approved ones.

Notes live in `GlossNote`, outside normalized block text. Promotion bundles
carry them with the edition. Public block payloads add a `notes` array; each
entry has `id`, `start`, `end`, `quote`, and `body`. Parallel block payloads add
`primary_notes` and `secondary_notes` with the same entry shape. Offsets are
Unicode code point positions in the respective complete block text. Consumers
must check the quote against the offset before showing a note. Empty arrays
mean that a block has no approved current notes.

The backend turns validated anchors into escaped `almonium-gloss` spans in its
shared book HTML. Web opens a margin card from the span; mobile opens a native
sheet. Both readers keep their sentence pairing interactions around the span.
