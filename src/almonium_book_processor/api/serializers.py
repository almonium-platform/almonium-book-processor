from __future__ import annotations

from rest_framework import serializers

from almonium_book_processor.catalog.models import ContentBlock, Edition, PipelineRun, Work
from almonium_book_processor.catalog.services import create_source_edition
from almonium_book_processor.ingest.source import SUPPORTED_SOURCE_EXTENSIONS


class WorkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Work
        fields = ("id", "slug", "title", "author", "original_language", "first_published_year")


class EditionSerializer(serializers.ModelSerializer):
    work = WorkSerializer(read_only=True)

    class Meta:
        model = Edition
        fields = (
            "id",
            "slug",
            "work",
            "source_edition_id",
            "title",
            "author",
            "language",
            "edition_type",
            "translator",
            "cefr_target",
            "status",
            "word_count",
            "confidence",
            "source_sha256",
            "published_at",
            "created_at",
            "updated_at",
        )


class EditionUploadSerializer(serializers.Serializer):
    source_file = serializers.FileField()
    work_slug = serializers.SlugField(max_length=160)
    work_title = serializers.CharField(max_length=500)
    author = serializers.CharField(max_length=300)
    original_language = serializers.CharField(max_length=35)
    edition_slug = serializers.SlugField(max_length=180)
    edition_title = serializers.CharField(max_length=500)
    language = serializers.CharField(max_length=35)
    edition_type = serializers.ChoiceField(choices=Edition.EditionType.choices)

    def validate_source_file(self, source):
        if not any(
            source.name.lower().endswith(extension) for extension in SUPPORTED_SOURCE_EXTENSIONS
        ):
            raise serializers.ValidationError("Only EPUB and TEI XML files are supported.")
        return source

    def create(self, validated_data):
        return create_source_edition(**validated_data)


class PipelineRunSerializer(serializers.ModelSerializer):
    edition_slug = serializers.CharField(source="edition.slug", read_only=True)

    class Meta:
        model = PipelineRun
        fields = (
            "id",
            "edition_id",
            "edition_slug",
            "stage",
            "status",
            "progress",
            "confidence",
            "summary",
            "error",
            "created_at",
            "started_at",
            "finished_at",
        )


class ContentBlockSerializer(serializers.ModelSerializer):
    chapter = serializers.IntegerField(source="chapter.sequence")

    class Meta:
        model = ContentBlock
        fields = (
            "id",
            "block_id",
            "chapter",
            "sequence",
            "block_type",
            "text",
            "sentences",
            "align_group",
            "source_ref",
            "attributes",
        )
