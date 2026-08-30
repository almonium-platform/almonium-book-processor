from django.urls import path

from almonium_book_processor.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("imports/private/", views.private_imports, name="private-imports"),
    path("upload/", views.upload_source, name="upload"),
    path("imports/legacy/", views.import_legacy, name="import-legacy"),
    path("editions/<uuid:edition_id>/", views.edition_detail, name="edition-detail"),
    path("editions/<uuid:edition_id>/reader/", views.edition_reader, name="edition-reader"),
    path(
        "editions/<uuid:edition_id>/blocks/<uuid:block_id>/edit/",
        views.edit_block_text,
        name="edit-block-text",
    ),
    path(
        "editions/<uuid:edition_id>/lexical/queue/",
        views.queue_lexical_analysis,
        name="queue-lexical-analysis",
    ),
    path(
        "editions/<uuid:edition_id>/source-qa/queue/",
        views.queue_source_quality_scan,
        name="queue-source-quality-scan",
    ),
    path(
        "editions/<uuid:edition_id>/source-qa/detached-initials/approve/",
        views.approve_detached_initials,
        name="approve-detached-initials",
    ),
    path(
        "editions/<uuid:edition_id>/source-qa/<uuid:finding_id>/apply/",
        views.apply_source_quality_finding,
        name="apply-source-quality-finding",
    ),
    path(
        "editions/<uuid:edition_id>/source-qa/<uuid:finding_id>/dismiss/",
        views.dismiss_source_quality_finding,
        name="dismiss-source-quality-finding",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/",
        views.alignment_review,
        name="alignment-review",
    ),
    path(
        "editions/<uuid:edition_id>/alignment/queue/",
        views.queue_source_alignment,
        name="queue-source-alignment",
    ),
    path(
        "editions/<uuid:edition_id>/translate/queue/",
        views.queue_parallel_translation,
        name="queue-parallel-translation",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/ai/queue/",
        views.queue_ai_alignment_review,
        name="queue-ai-alignment-review",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/ai/confirm-safe/",
        views.confirm_ai_safe_alignments,
        name="confirm-ai-safe-alignments",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/groups/<uuid:group_id>/accept/",
        views.accept_alignment_group,
        name="accept-alignment-group",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/chapters/accept/",
        views.accept_alignment_chapter,
        name="accept-alignment-chapter",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/repair/",
        views.repair_alignment,
        name="repair-alignment",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/gaps/<uuid:source_block_id>/translate/",
        views.translate_alignment_gap,
        name="translate-alignment-gap",
    ),
    path(
        "editions/<uuid:edition_id>/alignment-review/blocks/<uuid:block_id>/edit/",
        views.edit_alignment_target,
        name="edit-alignment-target",
    ),
    path(
        "editions/<uuid:edition_id>/warnings/<uuid:warning_id>/resolve/",
        views.resolve_warning,
        name="resolve-warning",
    ),
    path(
        "editions/<uuid:edition_id>/review/complete/",
        views.complete_edition_review,
        name="complete-edition-review",
    ),
    path(
        "editions/<uuid:edition_id>/publish/",
        views.publish_edition_to_almonium,
        name="publish-edition",
    ),
    path(
        "editions/<uuid:edition_id>/retry/",
        views.retry_failed_edition,
        name="retry-edition",
    ),
    path(
        "editions/<uuid:edition_id>/release-private/",
        views.release_private_import_to_owner,
        name="release-private-import",
    ),
]
