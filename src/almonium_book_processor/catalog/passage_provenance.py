"""Staff-only, recorded passage history. Never expose provider request bodies."""

import hashlib

from almonium_book_processor.catalog.models import AIRun, ContentBlockRevision


def passage_provenance(blocks):
    ids = {
        str(b.attributes.get(kind, {}).get("ai_run_id"))
        for b in blocks
        for kind in ("adaptation", "translation")
    }
    runs = {
        str(r.id): r
        for r in AIRun.objects.filter(id__in=[i for i in ids if i != "None"]).select_related(
            "model_configuration", "prompt_template", "pipeline_run"
        )
    }
    edition_runs = {}
    for run in AIRun.objects.filter(
        edition_id__in={b.edition_id for b in blocks},
        status="succeeded",
        prompt_template__name="literary-block-translation",
    ).select_related("model_configuration", "prompt_template", "pipeline_run"):
        edition_runs.setdefault(run.edition_id, []).append(run)
    revisions = {}
    for revision in ContentBlockRevision.objects.filter(block__in=blocks).order_by("-created_at"):
        revisions.setdefault(revision.block_id, revision)
    result = {}
    for block in blocks:
        adaptation = block.attributes.get("adaptation", {})
        translation = block.attributes.get("translation", {})
        metadata = adaptation or translation
        run = runs.get(str(metadata.get("ai_run_id")))
        scope = "Passage-linked" if run else "Not recorded"
        candidates = edition_runs.get(block.edition_id, [])
        if (
            run is None
            and translation
            and len(candidates) == 1
            and candidates[0].model_configuration.model == translation.get("model")
        ):
            run = candidates[0]
            scope = "Edition-level translation record; no passage link was stored"
        revision = revisions.get(block.id)
        value = {
            "block": block.block_id,
            "text_sha256": hashlib.sha256(block.text.encode()).hexdigest(),
            "source": block.source_ref or "Not recorded",
            "source_revision_at_generation": metadata.get("source_revision", "Not recorded"),
            "generation": "Adaptation"
            if adaptation
            else "Translation"
            if translation
            else "Imported source",
            "model": run.model_configuration.model
            if run
            else metadata.get("model", "Not recorded"),
            "prompt": f"{run.prompt_template.name} v{run.prompt_template.version}"
            if run
            else (
                f"v{metadata['prompt_version']}"
                if metadata.get("prompt_version")
                else "Not recorded for this passage"
            ),
            "generation_record_scope": scope,
            "generation_run": str(run.id) if run else "Not linked to this passage",
            "generation_pipeline": run.pipeline_run.processor_version
            if run and run.pipeline_run
            else "Not recorded",
            "latest_text_revision": str(revision.id) if revision else "No recorded edits",
            "revision_date": revision.created_at.isoformat() if revision else None,
            "revision_note": revision.notes if revision else None,
        }
        result[(block.edition_id, block.block_id)] = value
    return result
