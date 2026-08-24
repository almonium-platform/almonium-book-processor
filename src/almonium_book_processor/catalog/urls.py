from django.urls import path

from almonium_book_processor.catalog import views

app_name = "catalog"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("imports/private/", views.private_imports, name="private-imports"),
    path("upload/", views.upload_source, name="upload"),
    path("imports/legacy/", views.import_legacy, name="import-legacy"),
    path("editions/<uuid:edition_id>/", views.edition_detail, name="edition-detail"),
    path(
        "editions/<uuid:edition_id>/alignment-review/",
        views.alignment_review,
        name="alignment-review",
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
