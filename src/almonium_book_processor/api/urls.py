from django.urls import include, path
from rest_framework.routers import DefaultRouter

from almonium_book_processor.api.views import (
    EditionViewSet,
    PipelineRunViewSet,
    PrivateImportBlocksView,
    PrivateImportDetailView,
    PrivateImportView,
    PublishedEditionViewSet,
)

router = DefaultRouter()
router.register("editions", EditionViewSet, basename="edition")
router.register("runs", PipelineRunViewSet, basename="pipeline-run")
router.register("public/editions", PublishedEditionViewSet, basename="published-edition")

urlpatterns = [
    path("", include(router.urls)),
    path("internal/imports/", PrivateImportView.as_view(), name="private-import"),
    path(
        "internal/imports/<uuid:import_id>/",
        PrivateImportDetailView.as_view(),
        name="private-import-detail",
    ),
    path(
        "internal/imports/<uuid:import_id>/blocks/",
        PrivateImportBlocksView.as_view(),
        name="private-import-blocks",
    ),
]
