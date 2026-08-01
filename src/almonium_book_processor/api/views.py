from __future__ import annotations

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from almonium_book_processor.api.serializers import (
    ContentBlockSerializer,
    EditionSerializer,
    EditionUploadSerializer,
    PipelineRunSerializer,
)
from almonium_book_processor.catalog.models import Edition, PipelineRun
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    split_edition_sentences,
)


class EditionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Edition.objects.select_related("work", "source_edition")
    serializer_class = EditionSerializer
    permission_classes = [permissions.IsAdminUser]

    @action(
        detail=False,
        methods=["post"],
        parser_classes=[MultiPartParser, FormParser],
        serializer_class=EditionUploadSerializer,
    )
    def upload(self, request):
        serializer = EditionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edition = serializer.save()
        return Response(EditionSerializer(edition).data, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["get"])
    def blocks(self, request, pk=None):
        edition = self.get_object()
        blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")
        return Response(ContentBlockSerializer(blocks, many=True).data)

    @action(detail=True, methods=["post"])
    def split_sentences(self, request, pk=None):
        edition = self.get_object()
        split_edition_sentences.delay(str(edition.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"])
    def align_to_source(self, request, pk=None):
        edition = self.get_object()
        if edition.source_edition_id is None:
            return Response(
                {"source_edition": "This edition has no source edition."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        align_edition_to_source.delay(str(edition.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


class PipelineRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PipelineRun.objects.select_related("edition")
    serializer_class = PipelineRunSerializer
    permission_classes = [permissions.IsAdminUser]


class PublishedEditionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Edition.objects.filter(status=Edition.Status.PUBLISHED).select_related("work")
    serializer_class = EditionSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    @action(detail=True, methods=["get"])
    def blocks(self, request, slug=None):
        edition = self.get_object()
        blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")
        return Response(ContentBlockSerializer(blocks, many=True).data)
