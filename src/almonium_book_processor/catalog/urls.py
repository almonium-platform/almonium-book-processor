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
