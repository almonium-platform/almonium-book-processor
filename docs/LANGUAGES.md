# Languages

Support is per (language, feature), never a tier (decision 9). This page is
derived from `languages.py`, `config/settings.py`, the `worker` extra in
`pyproject.toml`, `processing/lexical.py`, `ai/output_language.py`, the
prompts and the calibration fixtures. Regenerate it when any of those changes;
`manage.py check --tag nlp` is the executable half of the table.

## The table

| Code | Language | spaCy model | wordfreq | simplemma | Fixtures | Books |
|---|---|---|---|---|---|---|
| bg | Bulgarian | — | yes | yes | | |
| ca | Catalan | ca_core_news_sm | yes | yes | | |
| cs | Czech | — | yes | yes | | |
| da | Danish | da_core_news_sm | yes | yes | | |
| de | German | de_core_news_sm | yes | yes | yes | |
| el | Greek | el_core_news_sm | yes | yes | | |
| en | English | en_core_web_sm | yes | yes | yes | originals, B2 adaptation |
| es | Spanish | es_core_news_sm | yes | yes | | |
| et | Estonian | — | no | yes | | |
| fi | Finnish | fi_core_news_sm | yes | yes | | |
| fr | French | fr_core_news_sm | yes | yes | | human translation, in review |
| ga | Irish | — | no | yes | | |
| hr | Croatian | hr_core_news_sm | as `sh` | as `hbs` | | |
| hu | Hungarian | — | yes | yes | | |
| is | Icelandic | — | yes | yes | | |
| it | Italian | it_core_news_sm | yes | yes | | |
| ja | Japanese | ja_core_news_sm | yes (cjk) | no; lemma from the SudachiPy tokenizer | | |
| ko | Korean | ko_core_news_sm | yes (cjk) | no; spaCy only | | |
| lt | Lithuanian | lt_core_news_sm | yes | yes | | |
| lv | Latvian | — | yes | yes | | |
| mk | Macedonian | mk_core_news_sm | yes | yes | | |
| mt | Maltese | — | no | no | | |
| nl | Dutch | nl_core_news_sm | yes | yes | | |
| no | Norwegian | nb_core_news_sm | as `nb` | as `nb` | | |
| pl | Polish | pl_core_news_sm | yes | yes | | |
| pt | Portuguese | pt_core_news_sm | yes | yes | | |
| ro | Romanian | ro_core_news_sm | yes | yes | | |
| ru | Russian | ru_core_news_sm | yes | yes | | |
| sk | Slovak | — | yes | yes | | |
| sl | Slovenian | sl_core_news_sm | yes | yes | | |
| sr | Serbian | — | no (`sh` is not mapped) | no | | |
| sv | Swedish | sv_core_news_sm | yes | yes | | |
| tr | Turkish | — | yes | yes | | |
| uk | Ukrainian | uk_core_news_sm | yes | yes | yes | machine translation of Frankenstein |
| zh | Chinese | zh_core_web_sm | yes (cjk) | no; uninflected, surface is the headword | | |

Every spaCy model named is pinned as a wheel in the `worker` extra, one per
`NLP_SPACY_MODELS` entry; a model can be overridden per language with
`NLP_SPACY_MODEL_<CODE>`. The registry also accepts the ISO 639-2 and common
EPUB/TEI aliases (`eng`, `deu`/`ger`, `fra`/`fre`, `nb`/`nn` → `no`, …) and
`normalize_language_code` collapses `en-GB` to `en`.

## What each feature needs

- **Ingestion** works for every code in the registry. Nothing is refused at
  upload for lack of NLP support.
- **Sentence splitting** (`processing/nlp.py`) uses the spaCy model when there
  is one and a blank-language sentencizer otherwise, so every language splits;
  only the quality differs.
- **Embeddings and offline alignment** use one multilingual model
  (`NLP_EMBEDDING_MODEL`, MiniLM by default) for every pair.
- **Vocabulary analysis** (`processing/lexical.py`) refuses to run without a
  spaCy model rather than inventing lemmas with a blank pipeline. simplemma is
  the fallback for a token the pipeline cannot lemmatize, and wordfreq gives
  the Zipf frequency; the two aliases above are resolved there. The eleven
  languages without a model (`bg cs et ga hu is lv mt sk sr tr`) are therefore
  ingestible but not analysable until a wheel is pinned.
- **Paid prompts** are language-parameterised: translation, alignment and
  metadata prompts are templated on the language names; chapter analysis uses
  the validated English v3 prompt for `en` and the localized v4 for every other
  code; same-language adaptation uses B2 v7 / B1 v5 for `en` and v8 / v6
  otherwise ([ADAPTATION_PILOT.md](ADAPTATION_PILOT.md), "Other languages").
- **Output-language gates** (`ai/output_language.py`) reject generated prose
  that does not validate as the edition language: langid for every code, with
  alphabet evidence plus Lingua for Ukrainian and Russian, `nb`/`nn` folded
  into `no`, confidence 0.8. Analysis and metadata fields are judged each on
  their own; rewritten book text (adapted blocks, audit corrections) is judged
  together and only once there are forty letters of it.
- **Difficulty calibration fixtures** exist for `en`, `de` and `uk` only, and
  have no non-English reference ratings yet ([CALIBRATION_FIXTURES.md](CALIBRATION_FIXTURES.md)).

## Evidence per language

- `en`: the whole adaptation record, judged and audited.
- `uk`: a machine translation with its own title page and chapter
  descriptions; chapter analysis in Ukrainian
  (`evidence/ukrainian-20260918/`). No adaptation judged or audited.
- `fr`: a human translation aligned and reviewed by inference; not published.
- Everything else: the table above and nothing more.

## Adding a language, or a model for one

1. Pin the spaCy wheel in the `worker` extra and add the code to
   `_SPACY_DEFAULT_MODELS` in `config/settings.py`.
2. Add a wordfreq or simplemma alias in `processing/lexical.py` if either
   knows the language under another code (`test_language_coverage.py` and
   `test_lexical.py` cover the mappings).
3. Rebuild the worker image and run `manage.py check --tag nlp`.
4. Ingest one real book, run vocabulary analysis and chapter analysis, and
   read the output before calling the language supported; add fixtures if the
   difficulty judge will be trusted for it.
