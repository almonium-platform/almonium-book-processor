from django.urls import include, path
from rest_framework.routers import DefaultRouter

from almonium_book_processor.api.views import (
    EditionViewSet,
    PipelineRunViewSet,
    PublishedEditionViewSet,
)

router = DefaultRouter()
router.register("editions", EditionViewSet, basename="edition")
router.register("runs", PipelineRunViewSet, basename="pipeline-run")
router.register("public/editions", PublishedEditionViewSet, basename="published-edition")

urlpatterns = [path("", include(router.urls))]
