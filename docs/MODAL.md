# Embeddings on Modal

The book worker on the OCI host is an ARM machine with no GPU. Offline sentence alignment
spends most of its time in the embedding model's forward pass (LaBSE above all), so that
pass can run on a Modal GPU instead. Everything else stays on the worker: sentence
splitting, chunking a text longer than the encoder window, the vector caches, and the
artifacts.

## What leaves the worker

Only public catalogue text. A call site that has checked its work is public opens
`remote_embeddings.public_text()`; only the offline sentence job does (it runs on public
works alone). The inferred block alignment of a new edition stays on the CPU, and private
uploads are embedded on the worker's own CPU whatever the setting says. Modal keeps nothing
after a call returns.

## What it costs

Nothing, by design: Modal is used only inside the Starter plan's free $30 of monthly
credits. Modal bills GPU seconds (an L4 is $0.000222/s) plus the container's start and its
idle minute after the last call, so a whole book is cents of credit. Before a run starts on
Modal, `catalog/modal_budget.py` adds this month's recorded spend to the run's estimate; a
run that would pass `MODAL_MONTHLY_BUDGET_USD` (25, under the credits because recorded cost
is an estimate) embeds on the worker's CPU instead, free and never held.

The hard cap behind it is Modal's own: set the workspace budget to $30 on the Usage &
Billing settings page. It caps usage before credits are applied, so the account cannot be
charged even if an estimate here is wrong. The alignment buttons show the price
when the backend is `modal` (`catalog/estimates.offline_alignment`) and show "No API cost"
when it is `local`.

Each run records its Modal use in `summary.embedding`: `modal_calls`, `modal_texts`,
`gpu_seconds`, `usd`. `./plan-manage spend_guard` and the dashboard's guard line add these
up. A pair's vectors are bought once: a finished pair's artifact is reused, and a retry only
re-embeds the window that the failed run had prefetched but not yet written.

## Measured (18 November 2026)

The Jekyll pairs with LaBSE, every text a run embeds (about 8,000 texts, 0.5 M characters
a pair), from the owner's desktop; nothing was written:

| Pair | Modal L4, warm | GPU seconds | CPU, desktop (16 cores, bf16) |
| --- | --- | --- | --- |
| EN-DE | 20.9 s | 2.0 | 42.9 s |
| EN-UK | 20.6 s | 2.1 | 51.2 s |

The GPU does its part in two seconds; the rest of the wall time is the worker tokenizing
each text locally and the vectors (about 24 MB a pair) coming back over the network. The
very first call after a deploy waited 13 minutes while Modal fetched the new image; later
starts are seconds. Modal billed $0.045 for four passes and the deploy, where the runs
recorded $0.085: the record errs high, as a budget against free credits should. The OCI
worker's ARM cores are slower than the desktop's, so the gain there should be larger;
measure it there before relying on it.

## Settings

| Variable | Meaning |
| --- | --- |
| `NLP_EMBEDDING_BACKEND` | `local` (default) or `modal` |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | The workspace token (Modal dashboard → Settings → API Tokens). A secret, kept in the infra vault. |
| `MODAL_ENVIRONMENT` | Optional Modal environment; Modal's default when empty |
| `MODAL_EMBEDDING_APP` | Deployed app name, `almonium-books-embeddings` |
| `MODAL_EMBEDDING_GPU` | The GPU the app was deployed with (`L4`); prices and run records read it |
| `MODAL_MONTHLY_BUDGET_USD` | Recorded Modal spend per calendar month past which runs embed on the CPU (25) |
| `NLP_EMBEDDING_PRECISION` | `auto` picks bf16 on the GPU (fp16 on a T4) |

Modal's client reads the token from the environment, so the worker needs no
`~/.modal.toml` and no `modal setup`. There is no `MODAL_TOKEN_PROFILE`;
`MODAL_PROFILE` only picks a section of `~/.modal.toml`, which a container does not have.

## Deploying the app

Deploy from a machine with the token, whenever `modal_apps/embeddings.py` changes and
before any environment switches to `modal`:

```bash
uvx --from 'modal>=1.6,<2' modal deploy modal_apps/embeddings.py
# a different GPU must be named in both places:
MODAL_EMBEDDING_GPU=A10 uvx --from 'modal>=1.6,<2' modal deploy modal_apps/embeddings.py
```

The image bakes in the weights of every model `offline_sentence_alignment.available_models()`
offers, and pins torch, sentence-transformers and transformers to the versions the CPU worker
runs. Add a model there before offering it in the admin.

## Switching an environment

1. Put the token in the infra vault and set `NLP_EMBEDDING_BACKEND=modal` for the
   environment (`../almonium-infra`).
2. Deploy, then queue one offline alignment and read its run summary's `embedding`.
3. Check the guard: `./plan-manage spend_guard`.

To go back to the CPU, set `NLP_EMBEDDING_BACKEND=local`. Vectors from the two backends
differ only by precision, which is part of every cache key and is recorded beside each
artifact.
