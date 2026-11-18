"""Bounded offline correspondence within an already aligned paragraph pair."""

import re
from collections import OrderedDict

import numpy as np
from django.conf import settings

from almonium_book_processor.processing.nlp import (
    align_embeddings,
    embed_texts,
    embedding_runtime,
)

VERSION = "offline-sentence-v10"

# The sentence stage aligns paragraphs of up to this many sentences a side. It stopped at
# 80 while its dynamic programme took a Python mean and cosine per cell; with the window
# table in nlp.align_embeddings 350 sentences take about a second, and a paragraph left
# without sentence anchors was refined as one region of hundreds of chunks (v9 confirmed
# nothing in Der Prozess's page-long paragraphs).
SENTENCE_LIMIT = 600


def _cover_groups(primary_count, secondary_count, groups):
    """Give every sentence a partner while retaining the embedding matches.

    The paragraph pair is already exact. An uncertain sentence correspondence is
    still useful for reading, provided it is kept marked as uncertain in the
    artifact. Positional groups fill only the intervals embeddings left open.
    """
    anchors = sorted(
        (g for g in groups if g["primary"] and g["secondary"]),
        key=lambda g: (g["primary"][0], g["secondary"][0]),
    )
    result = []
    p_cursor = s_cursor = 0

    def gap(p_end, s_end):
        nonlocal p_cursor, s_cursor
        primary = list(range(p_cursor, p_end))
        secondary = list(range(s_cursor, s_end))
        if primary and secondary:
            count = min(len(primary), len(secondary))
            for index in range(count):
                p_slice = primary[
                    index * len(primary) // count : (index + 1) * len(primary) // count
                ]
                s_slice = secondary[
                    index * len(secondary) // count : (index + 1) * len(secondary) // count
                ]
                result.append(
                    {
                        "primary": p_slice,
                        "secondary": s_slice,
                        "certain": False,
                        "acceptance": "positional_fallback",
                    }
                )
        elif primary or secondary:
            if result:
                result[-1]["primary"] = [*result[-1]["primary"], *primary]
                result[-1]["secondary"] = [*result[-1]["secondary"], *secondary]
                result[-1]["certain"] = False
            elif anchors:
                anchors[0].update(
                    primary=[*primary, *anchors[0]["primary"]],
                    secondary=[*secondary, *anchors[0]["secondary"]],
                    certain=False,
                )
        p_cursor, s_cursor = p_end, s_end

    for anchor in anchors:
        gap(anchor["primary"][0], anchor["secondary"][0])
        result.append(anchor)
        p_cursor = anchor["primary"][-1] + 1
        s_cursor = anchor["secondary"][-1] + 1
    gap(primary_count, secondary_count)
    return result


def sentence_texts(block):
    cursor = 0
    result = []
    for span in block.sentences:
        start, end = span.get("start"), span.get("end")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not cursor <= start < end <= len(block.text)
        ):
            raise ValueError("Invalid sentence offsets; rerun sentence splitting")
        if block.text[cursor:start].strip():
            raise ValueError("Sentence offsets omit text; rerun sentence splitting")
        result.append(block.text[start:end])
        cursor = end
    if block.text[cursor:].strip():
        raise ValueError("Sentence offsets omit text; rerun sentence splitting")
    return result


# Vectors this worker has computed, newest last, keyed by model, device, precision and text. An
# original paired with several companions is embedded once, and a run embeds ahead in
# large calls (prefetch) instead of one small call per paragraph pair.
_vectors: OrderedDict[tuple[str, str, str, str], np.ndarray] = OrderedDict()


def _key(model_name, text):
    # The device too: a vector from a Modal GPU must not be recorded as the worker's own.
    runtime = embedding_runtime()
    return (
        model_name or settings.NLP_EMBEDDING_MODEL,
        runtime.device,
        runtime.precision,
        text.strip(),
    )


def _normalized(texts, model_name):
    # float32, as the model returns them: the worker cache holds tens of thousands.
    vectors = np.asarray(
        embed_texts(texts, chunk_long=True, model_name=model_name), dtype=np.float32
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.where(norms, norms, np.float32(1))


def _remember(key, vector):
    _vectors[key] = vector
    _vectors.move_to_end(key)
    while len(_vectors) > max(settings.NLP_EMBEDDING_CACHE_TEXTS, 0):
        _vectors.popitem(last=False)


def prefetch(texts, model_name=None):
    """Embed every text not yet known, in calls of NLP_EMBEDDING_PREFETCH_TEXTS.

    A text already known is moved to the young end first: it is about to be read, and the
    new texts must push out what has been used, not what is needed next.
    """

    missing, seen = [], set()
    for text in texts:
        stripped = text.strip()
        if not stripped or stripped in seen:
            continue
        seen.add(stripped)
        key = _key(model_name, stripped)
        if key in _vectors:
            _vectors.move_to_end(key)
        else:
            missing.append(stripped)
    size = max(settings.NLP_EMBEDDING_PREFETCH_TEXTS, 1)
    for start in range(0, len(missing), size):
        window = missing[start : start + size]
        for text, vector in zip(window, _normalized(window, model_name), strict=True):
            _remember(_key(model_name, text), vector)


def pair_texts(primary, secondary):
    """Every text correspond() may embed for this paragraph pair."""

    if primary.text == secondary.text:
        return []
    texts = []
    for block in (primary, secondary):
        try:
            texts += sentence_texts(block)
            texts += [block.text[c["start"] : c["end"]] for s in clause_spans(block) for c in s]
        except ValueError:  # correspond() reports invalid offsets itself
            continue
    return texts


def _embed(texts, model_name, cache):
    """Vectors for texts: from this pair's own memo, then the worker's, then the model.

    Texts embedded in one call come back by position, so two equal strings in one call
    get the model's answer for each.
    """

    keys = [t.strip() for t in texts]
    known = {}
    for key in keys:
        if key in cache:
            known[key] = cache[key]
        elif (shared := _vectors.get(_key(model_name, key))) is not None:
            _vectors.move_to_end(_key(model_name, key))  # least recently used goes first
            known[key] = shared
    missing = [k for k in keys if k not in known]
    fresh = iter(())
    if missing:
        vectors = _normalized(missing, model_name)
        for key, vector in zip(missing, vectors, strict=True):
            cache[key] = vector
            _remember(_key(model_name, key), vector)
        fresh = iter(vectors)
    return (
        np.array([known[k] if k in known else next(fresh) for k in keys])
        if keys
        else np.zeros((0, 0))
    )


def _correspond(primary, secondary, model_name=None, cache=None):
    left, right = sentence_texts(primary), sentence_texts(secondary)
    if not left or not right:
        return {
            "groups": [],
            "method": "paragraph_fallback",
            "fallback_reason": "missing_sentences",
        }
    if primary.text == secondary.text and primary.sentences == secondary.sentences:
        return {
            "method": "identical_text",
            "groups": [
                {"primary": [i], "secondary": [i], "certain": True} for i in range(len(left))
            ],
        }
    if len(left) == len(right) == 1:
        return {
            "method": "inherited_single_sentence",
            "groups": [{"primary": [0], "secondary": [0], "certain": True}],
        }
    # Bound CPU and avoid quietly feeding oversized sentences to a truncating encoder.
    if max(len(left), len(right)) > SENTENCE_LIMIT or max(map(len, left + right)) > 12000:
        return {"groups": [], "method": "paragraph_fallback", "fallback_reason": "size_limit"}
    try:
        vectors = _embed(left + right, model_name, {} if cache is None else cache)
    except ValueError as error:
        if str(error) != "Sentence exceeds embedding token limit":
            raise
        return {"groups": [], "method": "paragraph_fallback", "fallback_reason": "token_limit"}
    candidates = align_embeddings(
        vectors[: len(left)],
        vectors[len(left) :],
        source_lengths=list(map(len, left)),
        target_lengths=list(map(len, right)),
        minimum_confidence=0.65,
        sentence_groups=True,
    )
    groups = []
    similarities = vectors[: len(left)] @ vectors[len(left) :].T
    for c in candidates:
        margin = None
        # Lower-score acceptance is limited to distinct reciprocal 1:1 matches.
        # Split/merged groups keep the existing stricter acceptance rule.
        if len(c.source_indices) == len(c.target_indices) == 1:
            i, j = c.source_indices[0], c.target_indices[0]
            competitors = np.concatenate(
                [np.delete(similarities[i], j), np.delete(similarities[:, j], i)]
            )
            margin = float(similarities[i, j]) - (
                float(competitors.max()) if competitors.size else 1.0
            )
        relative = c.confidence >= 0.75 and margin is not None and margin >= 0.10
        certain = c.confidence >= 0.82 or relative
        groups.append(
            {
                "primary": list(c.source_indices),
                "secondary": list(c.target_indices),
                "certain": certain,
                "similarity": round(c.confidence, 4),
                "margin": round(margin, 4) if margin is not None else None,
                "acceptance": "absolute"
                if c.confidence >= 0.82
                else "reciprocal_margin"
                if relative
                else "uncertain",
            }
        )
    for side, texts in (("primary", left), ("secondary", right)):
        used = {i for group in groups for i in group[side]}
        for i in range(len(texts)):
            if i not in used:
                groups.append(
                    {
                        "primary": [i] if side == "primary" else [],
                        "secondary": [i] if side == "secondary" else [],
                        "certain": False,
                    }
                )
    return {
        "groups": groups,
        "method": "offline_embeddings",
        "highlight_threshold": 0.82,
        "relative_minimum": 0.75,
        "reciprocal_margin": 0.10,
    }


# A clause boundary is punctuation followed by space. A semicolon separates
# independent clauses, so two words either side suffice; a comma, colon or dash
# also separates short list items and parentheticals, so each side needs four
# words before it stands as a chunk ("Spiel, Trotz, Genuß" stays whole; a longer
# list split the two languages differently merges back in _refine). German
# commas are obligatory before subordinate clauses, which is what keeps a
# verb-final clause in one chunk with its verb.
_BOUNDARY = re.compile(r"(?P<mark>[;:,]|\s[—–]|--)\s+")
_MINIMUM_WORDS = {";": 2}
_DEFAULT_MINIMUM_WORDS = 4
# A refined chunk pair must resemble itself this much, and beat every crossing
# pairing inside its sentence group by this margin; otherwise it merges with a
# neighbour. Measured on DE, FR, EN, ES and UK pairs (docs/SENTENCE_ALIGNMENT.md).
CHUNK_MINIMUM_SIMILARITY = 0.6
CHUNK_MINIMUM_MARGIN = 0.2
CHUNK_CERTAIN_SIMILARITY = 0.7
# Inside a region the sentence matcher did not confirm, only a small chunk pair
# can be confirmed on its own evidence; a large one is what is left over.
CHUNK_CERTAIN_SIZE = 3
# A chunk pair need only beat the pairings of the groups this close on either side. An
# in-order alignment cannot mistake a chunk for one forty chunks away, but against the
# whole of a page-long region some repeated phrase ("sagte K.") always comes close, and
# every pair merged away. Six covers every chunk of 99.4% of sentences (2026-11-18).
CHUNK_MARGIN_WINDOW = 6


def _words(text):
    return len(re.findall(r"\w+", text))


def clause_spans(block):
    """Clause-sized chunks of each sentence, preserving text and Unicode offsets.

    Returns, per sentence, the list of its chunk spans; the trailing space of a
    chunk belongs to the gap, never to the chunk.
    """
    sentence_texts(block)  # Validate the original segmentation first.
    result = []
    for sentence in block.sentences:
        start, end = sentence["start"], sentence["end"]
        cuts = [start]
        for match in _BOUNDARY.finditer(block.text[start:end]):
            minimum = _MINIMUM_WORDS.get(match["mark"], _DEFAULT_MINIMUM_WORDS)
            boundary = start + match.end()
            if _words(block.text[cuts[-1] : boundary]) < minimum:
                continue
            if _words(block.text[boundary:end]) < minimum:
                continue
            cuts.append(boundary)
        spans = []
        for index, cut in enumerate(cuts):
            stop = cuts[index + 1] if index + 1 < len(cuts) else end
            while stop > cut and block.text[stop - 1].isspace():
                stop -= 1
            spans.append({"start": cut, "end": stop})
        result.append(spans)
    return result


def _refine(primary, secondary, p_texts, s_texts):
    """Split one sentence group into the smallest chunk pairs that stand on their own.

    A monotonic alignment proposes chunk pairs; a pair that is weak, or that
    resembles a crossing partner nearly as well as its own (a clause moved to
    the other end of the sentence, a verb-final tail), merges with the neighbour
    it fits best, until every pair stands or one group is left.
    """

    primary = np.asarray(primary, dtype=float)
    secondary = np.asarray(secondary, dtype=float)

    def unit(matrix, indexes):
        mean = matrix[indexes].mean(axis=0)
        norm = np.linalg.norm(mean)
        return mean / norm if norm else mean

    def similarity(group):
        return float(unit(primary, group[0]) @ unit(secondary, group[1]))

    whole = [list(range(len(primary))), list(range(len(secondary)))]
    if len(primary) == 1 and len(secondary) == 1:
        return [(*whole, similarity(whole), None)]
    candidates = align_embeddings(
        primary,
        secondary,
        source_lengths=list(map(len, p_texts)),
        target_lengths=list(map(len, s_texts)),
        minimum_confidence=0.3,
        sentence_groups=True,
    )
    groups = []
    p_cursor = s_cursor = 0
    for candidate in candidates:
        p_indexes = list(range(p_cursor, candidate.source_indices[-1] + 1))
        s_indexes = list(range(s_cursor, candidate.target_indices[-1] + 1))
        groups.append([p_indexes, s_indexes])
        p_cursor, s_cursor = p_indexes[-1] + 1, s_indexes[-1] + 1
    if not groups:
        return [(*whole, similarity(whole), None)]
    groups[-1][0].extend(range(p_cursor, len(primary)))
    groups[-1][1].extend(range(s_cursor, len(secondary)))

    # Every group's two sides as unit means, and the similarity of every primary side
    # to every secondary side: the diagonal is a group's own similarity, the cells near
    # it its crossing pairings with its neighbours. A merge replaces two rows and
    # columns with one, so a region of n chunks costs n² once, not n³ per pass (Kafka's
    # page-long paragraphs held the aligner for half an hour).
    p_units = [unit(primary, g[0]) for g in groups]
    s_units = [unit(secondary, g[1]) for g in groups]
    matrix = np.array(p_units) @ np.array(s_units).T

    def scores():
        own = np.diag(matrix).copy()
        count = len(groups)
        if count == 1:
            return own, [None]
        # Group i against group i+d: matrix[i, i+d] and matrix[i+d, i], for both.
        rivals = np.full(count, -np.inf)
        for distance in range(1, min(CHUNK_MARGIN_WINDOW, count - 1) + 1):
            crossing = np.maximum(np.diagonal(matrix, distance), np.diagonal(matrix, -distance))
            rivals[:-distance] = np.maximum(rivals[:-distance], crossing)
            rivals[distance:] = np.maximum(rivals[distance:], crossing)
        return own, own - np.maximum(rivals, -1.0)

    while len(groups) > 1:
        own, margins = scores()
        worst = min(
            range(len(groups)),
            key=lambda i: min(own[i] - CHUNK_MINIMUM_SIMILARITY, margins[i] - CHUNK_MINIMUM_MARGIN),
        )
        if own[worst] >= CHUNK_MINIMUM_SIMILARITY and margins[worst] >= CHUNK_MINIMUM_MARGIN:
            break
        options = []
        for neighbour in (worst - 1, worst + 1):
            if 0 <= neighbour < len(groups):
                a, b = sorted((worst, neighbour))
                merged = [groups[a][0] + groups[b][0], groups[a][1] + groups[b][1]]
                options.append((similarity(merged), a, b, merged))
        _, a, b, merged = max(options)
        groups[a : b + 1] = [merged]
        p_units[a : b + 1] = [unit(primary, merged[0])]
        s_units[a : b + 1] = [unit(secondary, merged[1])]
        matrix = np.delete(np.delete(matrix, b, axis=0), b, axis=1)
        matrix[a, :] = p_units[a] @ np.array(s_units).T
        matrix[:, a] = np.array(p_units) @ s_units[a]
    if len(groups) == 1:
        return [(*groups[0], similarity(groups[0]), None)]
    own, margins = scores()
    return [(g[0], g[1], float(own[i]), float(margins[i])) for i, g in enumerate(groups)]


def correspond(primary, secondary, model_name=None):
    cache = {}
    coarse = _correspond(primary, secondary, model_name, cache)
    left, right = clause_spans(primary), clause_spans(secondary)
    coarse["groups"] = _cover_groups(len(left), len(right), coarse["groups"])
    if all(len(spans) == 1 for spans in left + right):
        return coarse
    p_spans = [span for spans in left for span in spans]
    s_spans = [span for spans in right for span in spans]
    p_of, s_of = [], []
    for spans, of in ((left, p_of), (right, s_of)):
        cursor = 0
        for chunk_spans in spans:
            of.append(list(range(cursor, cursor + len(chunk_spans))))
            cursor += len(chunk_spans)
    p_texts = [primary.text[s["start"] : s["end"]] for s in p_spans]
    s_texts = [secondary.text[s["start"] : s["end"]] for s in s_spans]
    identical = coarse.get("method") == "identical_text"
    vectors = [] if identical else _embed(p_texts + s_texts, model_name, cache)
    # Consecutive unconfirmed sentence groups are refined as one region: where the
    # two languages put their sentence boundaries in different places, the
    # sentence matcher's guess is wrong, and a chunk must be free to find its
    # partner across that boundary.
    regions = []
    for group in coarse["groups"]:
        if regions and not group["certain"] and not regions[-1][-1]["certain"]:
            regions[-1].append(group)
        else:
            regions.append([group])
    groups = []
    for region in regions:
        parent = region[0]
        p_indexes = [c for g in region for i in g["primary"] for c in p_of[i]]
        s_indexes = [c for g in region for i in g["secondary"] for c in s_of[i]]
        as_sentences = [
            {
                **g,
                "primary": [c for i in g["primary"] for c in p_of[i]],
                "secondary": [c for i in g["secondary"] for c in s_of[i]],
                "granularity": "sentence",
            }
            for g in region
        ]
        if identical:
            groups.extend(
                {"primary": [p], "secondary": [s], "certain": True, "granularity": "clause"}
                for p, s in zip(p_indexes, s_indexes, strict=True)
            )
            continue
        if len(region) == 1 and (
            len(p_indexes) == len(parent["primary"]) and len(s_indexes) == len(parent["secondary"])
        ):
            groups.extend(as_sentences)
            continue
        refined = _refine(
            [vectors[i] for i in p_indexes],
            [vectors[len(p_texts) + i] for i in s_indexes],
            [p_texts[i] for i in p_indexes],
            [s_texts[i] for i in s_indexes],
        )
        if len(refined) == 1:
            groups.extend(as_sentences)
            continue
        for fine_p, fine_s, similarity, fine_margin in refined:
            groups.append(
                {
                    "primary": [p_indexes[i] for i in fine_p],
                    "secondary": [s_indexes[i] for i in fine_s],
                    # Every chunk pair stood against its crossing partners. It is
                    # confirmed when its sentence group was, or when it is small
                    # and strong on its own; a large pair left over in an
                    # unconfirmed region is a remainder, not a match.
                    "certain": parent["certain"]
                    or (
                        similarity >= CHUNK_CERTAIN_SIMILARITY
                        and max(len(fine_p), len(fine_s)) <= CHUNK_CERTAIN_SIZE
                    ),
                    "similarity": round(similarity, 4),
                    "margin": round(fine_margin, 4),
                    "acceptance": "chunk_refinement",
                    "granularity": "clause",
                }
            )
    return {
        **coarse,
        "groups": groups,
        "primary_spans": p_spans,
        "secondary_spans": s_spans,
        "segmentation": "punctuation-clauses-v1",
    }
