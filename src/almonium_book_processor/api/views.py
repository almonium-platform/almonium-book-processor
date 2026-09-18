from __future__ import annotations

import hmac
import os

from django.http import FileResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from almonium_book_processor.api.serializers import (
    ContentBlockSerializer,
    EditionSerializer,
    EditionUploadSerializer,
    LibraryIngestSerializer,
    PipelineRunSerializer,
    PrivateImportMetadataSerializer,
    PrivateImportSerializer,
    TranslationEstimateSerializer,
    TranslationJobSerializer,
)
from almonium_book_processor.catalog.metadata import confirm_metadata, metadata_payload
from almonium_book_processor.catalog.models import (
    BlockAlignment,
    Edition,
    EditionTombstone,
    PipelineRun,
    Work,
)
from almonium_book_processor.catalog.promotion import (
    PromotionError,
    accepted_promotion_token,
    capabilities,
    import_bundle,
    queue_publications,
)
from almonium_book_processor.catalog.promotion_client import TOKEN_HEADER as PROMOTION_TOKEN_HEADER
from almonium_book_processor.catalog.purge import purge_edition
from almonium_book_processor.catalog.services import create_library_ingest
from almonium_book_processor.catalog.spend import ai_spend
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    split_edition_sentences,
)
from almonium_book_processor.catalog.translation_jobs import (
    JobConflict,
    JobNotFound,
    cancel_translation,
    estimate_translation,
    library_ingest,
    library_ingest_status,
    start_translation_job,
    translation_job,
    translation_status,
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
        if edition.inferred_alignment_source is None:
            return Response(
                {"edition": "Only a standalone edition with a canonical text can be aligned."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        align_edition_to_source.delay(str(edition.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)


class PipelineRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PipelineRun.objects.select_related("edition")
    serializer_class = PipelineRunSerializer
    permission_classes = [permissions.IsAdminUser]


class InternalBooksPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        expected = os.getenv("ALMONIUM_BOOKS_PUBLISHER_TOKEN", "")
        provided = request.headers.get("X-Almonium-Books-Token", "")
        return bool(expected and provided and hmac.compare_digest(expected, provided))


class PrivateImportView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = PrivateImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        edition = serializer.save()
        return Response(_private_import_payload(edition), status=status.HTTP_202_ACCEPTED)


class PrivateImportDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request, import_id):
        edition = _private_import(import_id, request.query_params.get("owner_id"))
        return Response(_private_import_payload(edition))

    def delete(self, request, import_id):
        """Destroy an owner's import at the owner's request.

        A private import is never published, so nothing outside the owner's own
        library refers to it and there is nothing to coordinate. The upload, the
        normalized text, and the book's words inside AI payloads all go; the
        token ledger keeps what the processing cost.
        """

        edition = _private_import(import_id, request.query_params.get("owner_id"))
        purge_edition(edition, reason=EditionTombstone.Reason.OWNER_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrivateImportMetadataView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def put(self, request, import_id):
        edition = _private_import(import_id, request.query_params.get("owner_id"))
        serializer = PrivateImportMetadataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        clear_year = "publication_year" in fields and fields["publication_year"] is None
        confirm_metadata(edition, **fields, clear_publication_year=clear_year)
        edition.refresh_from_db()
        return Response(_private_import_payload(edition))


class PrivateImportBlocksView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request, import_id):
        edition = _private_import(import_id, request.query_params.get("owner_id"))
        if edition.status != Edition.Status.READY:
            return Response(
                {"detail": "Private book content is not ready."},
                status=status.HTTP_409_CONFLICT,
            )
        blocks = edition.blocks.select_related("chapter").order_by("chapter__sequence", "sequence")
        return Response(ContentBlockSerializer(blocks, many=True).data)


class PrivateImportSourceView(APIView):
    """The owner's upload, streamed back for a reviewer; ownership is checked first."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request, import_id):
        edition = _private_import(import_id, request.query_params.get("owner_id"))
        if not edition.source_file:
            raise NotFound("Private import has no source file.")
        filename = os.path.basename(edition.source_file.name)
        return FileResponse(edition.source_file.open("rb"), as_attachment=True, filename=filename)


class TranslationEstimateView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request):
        serializer = TranslationEstimateSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(estimate_translation(**serializer.validated_data))
        except JobNotFound as error:
            raise NotFound(str(error)) from error
        except ValueError as error:
            raise ValidationError({"detail": str(error)}) from error


class TranslationJobView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def post(self, request):
        serializer = TranslationJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            edition, created = start_translation_job(**serializer.validated_data)
        except JobNotFound as error:
            raise NotFound(str(error)) from error
        except ValueError as error:
            raise ValidationError({"detail": str(error)}) from error
        return Response(
            translation_status(edition),
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class TranslationJobDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request, edition_id):
        return Response(translation_status(_translation_job(edition_id)))


class TranslationJobCancelView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def post(self, request, edition_id):
        edition = _translation_job(edition_id)
        try:
            cancel_translation(edition)
        except JobConflict as error:
            return Response({"detail": str(error)}, status=status.HTTP_409_CONFLICT)
        return Response(translation_status(edition))


class LibraryIngestView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def post(self, request):
        serializer = LibraryIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            edition, created = create_library_ingest(**serializer.validated_data)
        except LookupError as error:
            raise NotFound(str(error)) from error
        return Response(
            library_ingest_status(edition),
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class LibraryIngestDetailView(APIView):
    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request, edition_id):
        try:
            edition = library_ingest(edition_id)
        except JobNotFound as error:
            raise NotFound(str(error)) from error
        return Response(library_ingest_status(edition))


def _translation_job(edition_id):
    try:
        return translation_job(edition_id)
    except JobNotFound as error:
        raise NotFound(str(error)) from error


class InternalAiSpendView(APIView):
    """The token ledger summed for the API's spend page; the API owns the window."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [InternalBooksPermission]

    def get(self, request):
        since = _aware_datetime(request.query_params.get("since"), "since")
        until_raw = request.query_params.get("until")
        until = _aware_datetime(until_raw, "until") if until_raw else timezone.now()
        if since >= until:
            raise ValidationError({"since": "must be before until"})
        return Response(ai_spend(since, until))


class PromotionPermission(permissions.BasePermission):
    """The token this deployment was given for promotions, and nothing else.

    It is deliberately not the publisher secret: that one guards what the
    product API may do here, and it would otherwise have to be copied to every
    machine that promotes.
    """

    def has_permission(self, request, view):
        expected = accepted_promotion_token()
        provided = request.headers.get(PROMOTION_TOKEN_HEADER, "")
        return bool(expected and provided and hmac.compare_digest(expected, provided))


class PromotionCapabilitiesView(APIView):
    """What this deployment runs, so a source can tell whether its bundle fits."""

    authentication_classes = [SessionAuthentication]
    permission_classes = [PromotionPermission]

    def get(self, request):
        return Response(capabilities(request.query_params.getlist("slug")))


class PromotionImportView(APIView):
    """Land an edition bundle another deployment pushed here.

    The whole bundle is written in one transaction before the response, so a
    2xx means the edition is readable here and a 4xx means nothing changed.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [PromotionPermission]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        upload = request.FILES.get("bundle")
        if upload is None:
            return Response(
                {"message": "An edition bundle is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        publish = str(request.data.get("publish", "")).lower() in {"1", "true", "yes", "on"}
        try:
            result = import_bundle(upload.read())
        except PromotionError as error:
            return Response({"message": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        if publish:
            result["publish_queued"] = queue_publications(result["imported"] + result["skipped"])
        return Response(result)


def _aware_datetime(value, name):
    parsed = parse_datetime(value) if value else None
    if parsed is None or timezone.is_naive(parsed):
        raise ValidationError({name: "an ISO 8601 datetime with a timezone is required"})
    return parsed


def _private_import(import_id, owner_id):
    if not owner_id:
        raise NotFound("Private import not found.")
    try:
        return Edition.objects.select_related("work").get(
            id=import_id,
            work__visibility=Work.Visibility.PRIVATE,
            work__owner_id=owner_id,
        )
    except (Edition.DoesNotExist, ValueError) as error:
        raise NotFound("Private import not found.") from error


def _private_import_payload(edition):
    latest_run = edition.pipeline_runs.order_by("-created_at").first()
    return {
        "id": edition.id,
        "title": edition.title,
        "author": edition.author,
        "description": edition.work.description,
        "language": edition.language,
        "publication_year": edition.work.publication_year,
        "status": edition.status,
        "progress": latest_run.progress if latest_run else 0,
        "error": latest_run.error if latest_run else "",
        "word_count": edition.word_count,
        "metadata": metadata_payload(edition),
        "created_at": edition.created_at,
        "updated_at": edition.updated_at,
    }


class PublishedEditionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Edition.objects.filter(
        status=Edition.Status.PUBLISHED,
        work__visibility=Work.Visibility.PUBLIC,
    ).select_related("work")
    serializer_class = EditionSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "slug"

    @action(detail=True, methods=["get"])
    def chapters(self, request, slug=None):
        from almonium_book_processor.catalog.public_chapters import public_chapters

        return Response(public_chapters(self.get_object()))

    @action(detail=True, methods=["get"], url_path=r"chapters/(?P<sequence>\d+)/vocabulary")
    def chapter_vocabulary(self, request, slug=None, sequence=None):
        from django.shortcuts import get_object_or_404

        from almonium_book_processor.catalog.public_vocabulary import public_vocabulary

        edition = self.get_object()
        chapter = get_object_or_404(edition.chapters, sequence=sequence)
        return Response(public_vocabulary(edition, chapter))

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

        from almonium_book_processor.catalog.parallel_content import inherited_payload

        inherited = inherited_payload(edition, other)
        if inherited is not None:
            return Response(inherited)

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
                    "chapter_title": primary.chapter.title,
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
