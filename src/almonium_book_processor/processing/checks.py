"""Startup checks for the offline NLP stack.

The lexical stage decides how rare a word is from its lemma. A spaCy pipeline
without a lemmatizer produces no lemma, the fallback lemmatizer invents one,
and the whole filter then judges a word that is not in the book. That shipped
once, so the models are a checked deployment requirement, not a nice-to-have.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage, Error, Info, register

LEMMATIZER_PIPES = {"lemmatizer", "trainable_lemmatizer"}


@register("nlp")
def check_spacy_models(app_configs: Any, **kwargs: Any) -> list[CheckMessage]:
    try:
        import spacy
    except ImportError:
        return [
            Info(
                "spaCy is not installed, so the configured models were not verified.",
                hint="Only the worker image needs them: pip install '.[worker]'.",
                id="processing.I001",
            )
        ]

    messages: list[CheckMessage] = []
    for language, model_name in sorted(settings.NLP_SPACY_MODELS.items()):
        try:
            pipeline = spacy.load(model_name, exclude=["ner"])
        except OSError:
            messages.append(
                Error(
                    f"The spaCy model {model_name!r} for {language!r} is not installed.",
                    hint=f"python -m spacy download {model_name}",
                    id="processing.E001",
                )
            )
            continue
        if not LEMMATIZER_PIPES & set(pipeline.pipe_names):
            messages.append(
                Error(
                    f"The spaCy model {model_name!r} for {language!r} has no lemmatizer; "
                    f"its pipeline is {list(pipeline.pipe_names)}.",
                    hint="Vocabulary analysis needs lemmas, not just tokens.",
                    id="processing.E002",
                )
            )
    return messages
