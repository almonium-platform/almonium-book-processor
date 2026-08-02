from __future__ import annotations

from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from almonium_book_processor.api.serializers import (
    ContentBlockSerializer,
    EditionSerializer,
    EditionUploadSerializer,
    PipelineRunSerializer,
)
from almonium_book_processor.catalog.models import BlockAlignment, Edition, PipelineRun
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

    @action(
        detail=True,
        methods=["get"],
        url_path=r"parallel/(?P<other_slug>[^/.]+)",
    )
    def parallel(self, request, slug=None, other_slug=None):
        edition = self.get_object()
        try:
            other = self.queryset.get(slug=other_slug, work=edition.work)
        except Edition.DoesNotExist as error:
            raise NotFound("Published edition variant not found.") from error

        alignments = BlockAlignment.objects.filter(
            source_edition=other,
            target_edition=edition,
        ).select_related("source_block__chapter", "target_block__chapter")
        primary_side = "target"
        if not alignments.exists():
            alignments = BlockAlignment.objects.filter(
                source_edition=edition,
                target_edition=other,
            ).select_related("source_block__chapter", "target_block__chapter")
            primary_side = "source"
        if not alignments.exists():
            raise NotFound("Published editions have no reviewed alignment.")

        order_fields = (
            ("target_block__chapter__sequence", "target_block__sequence")
            if primary_side == "target"
            else ("source_block__chapter__sequence", "source_block__sequence")
        )
        blocks = []
        for alignment in alignments.order_by(*order_fields):
            primary = alignment.target_block if primary_side == "target" else alignment.source_block
            secondary = (
                alignment.source_block if primary_side == "target" else alignment.target_block
            )
            blocks.append(
                {
                    "chapter": primary.chapter.sequence,
                    "sequence": primary.sequence,
                    "block_type": primary.block_type,
                    "primary_text": primary.text,
                    "secondary_text": secondary.text,
                }
            )
        return Response(
            {
                "primary_language": edition.language,
                "secondary_language": other.language,
                "blocks": blocks,
            }
        )
