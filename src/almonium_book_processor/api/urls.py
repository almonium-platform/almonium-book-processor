from django.urls import include, path
from rest_framework.routers import DefaultRouter

from almonium_book_processor.api.views import (
    EditionViewSet,
    InternalAiSpendView,
    LibraryIngestDetailView,
    LibraryIngestView,
    PipelineRunViewSet,
    PrivateImportBlocksView,
    PrivateImportDetailView,
    PrivateImportMetadataView,
    PrivateImportSourceView,
    PrivateImportView,
    PublishedEditionViewSet,
    TranslationEstimateView,
    TranslationJobCancelView,
    TranslationJobDetailView,
    TranslationJobView,
)

router = DefaultRouter()
router.register("editions", EditionViewSet, basename="edition")
router.register("runs", PipelineRunViewSet, basename="pipeline-run")
router.register("public/editions", PublishedEditionViewSet, basename="published-edition")

urlpatterns = [
    path("", include(router.urls)),
    path("internal/ai-spend/", InternalAiSpendView.as_view(), name="internal-ai-spend"),
    path("internal/imports/", PrivateImportView.as_view(), name="private-import"),
    path(
        "internal/imports/<uuid:import_id>/",
        PrivateImportDetailView.as_view(),
        name="private-import-detail",
    ),
    path(
        "internal/imports/<uuid:import_id>/metadata/",
        PrivateImportMetadataView.as_view(),
        name="private-import-metadata",
    ),
    path(
        "internal/imports/<uuid:import_id>/blocks/",
        PrivateImportBlocksView.as_view(),
        name="private-import-blocks",
    ),
    path(
        "internal/imports/<uuid:import_id>/source/",
        PrivateImportSourceView.as_view(),
        name="private-import-source",
    ),
    path(
        "internal/translations/estimate/",
        TranslationEstimateView.as_view(),
        name="translation-estimate",
    ),
    path("internal/translations/", TranslationJobView.as_view(), name="translation-job"),
    path(
        "internal/translations/<uuid:edition_id>/",
        TranslationJobDetailView.as_view(),
        name="translation-job-detail",
    ),
    path(
        "internal/translations/<uuid:edition_id>/cancel/",
        TranslationJobCancelView.as_view(),
        name="translation-job-cancel",
    ),
    path("internal/library-ingests/", LibraryIngestView.as_view(), name="library-ingest"),
    path(
        "internal/library-ingests/<uuid:edition_id>/",
        LibraryIngestDetailView.as_view(),
        name="library-ingest-detail",
    ),
]
