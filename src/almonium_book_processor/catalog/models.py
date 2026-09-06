from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models

from almonium_book_processor.languages import LANGUAGE_CHOICES


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Work(TimestampedModel):
    class Visibility(models.TextChoices):
        PUBLIC = "public", "Public catalog"
        PRIVATE = "private", "Private import"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    original_language = models.CharField(max_length=35, choices=LANGUAGE_CHOICES)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    cover_url = models.URLField(max_length=1000, blank=True)
    visibility = models.CharField(
        max_length=10,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )
    owner_id = models.UUIDField(null=True, blank=True)
    owner_label = models.CharField(max_length=150, blank=True)
    # Private imports: who supplied each bibliographic field ("user", "source",
    # or "ai"), and when detection finished so the owner can be asked to confirm.
    metadata_provenance = models.JSONField(default=dict, blank=True)
    metadata_detected_at = models.DateTimeField(null=True, blank=True)
    metadata_confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["author", "title"]

    def __str__(self) -> str:
        return f"{self.author} — {self.title}"


def source_upload_path(instance: Edition, filename: str) -> str:
    extension = Path(filename).suffix.lower()
    return f"sources/{instance.id}/{uuid.uuid4()}{extension}"


class Edition(TimestampedModel):
    class CEFRLevel(models.TextChoices):
        A1 = "A1", "A1"
        A2 = "A2", "A2"
        B1 = "B1", "B1"
        B2 = "B2", "B2"
        C1 = "C1", "C1"
        C2 = "C2", "C2"

    class EditionType(models.TextChoices):
        ORIGINAL = "original", "Original"
        HUMAN_TRANSLATION = "human_translation", "Human translation"
        MACHINE_TRANSLATION = "machine_translation", "Machine translation"
        ADAPTATION = "adaptation", "Level adaptation"
        ABRIDGEMENT = "abridgement", "Abridgement"

    class ParallelRole(models.TextChoices):
        """How this edition participates in the work's canonical block tree."""

        CANONICAL = "canonical", "Canonical original"
        PARALLEL = "parallel", "Parallel edition"
        STANDALONE = "standalone", "Standalone edition"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        REVIEW = "review", "Needs review"
        READY = "ready", "Ready"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=180, unique=True)
    work = models.ForeignKey(Work, related_name="editions", on_delete=models.PROTECT)
    source_edition = models.ForeignKey(
        "self",
        related_name="derived_editions",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300)
    language = models.CharField(max_length=35, choices=LANGUAGE_CHOICES)
    edition_type = models.CharField(
        max_length=32,
        choices=EditionType.choices,
        default=EditionType.ORIGINAL,
    )
    translator = models.CharField(max_length=300, blank=True)
    cefr_level = models.CharField(
        max_length=2,
        choices=CEFRLevel.choices,
        null=True,
        blank=True,
    )
    parallel_role = models.CharField(
        max_length=12,
        choices=ParallelRole.choices,
        default=ParallelRole.CANONICAL,
        help_text=(
            "Canonical editions root the block tree. Parallel editions are generated "
            "block-for-block from the canonical text and can be read side by side. "
            "Standalone editions are read on their own and are never block-synchronised."
        ),
    )
    schema_version = models.PositiveSmallIntegerField(default=3)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    word_count = models.PositiveIntegerField(default=0)
    source_file = models.FileField(
        upload_to=source_upload_path,
        validators=[FileExtensionValidator(["epub", "xml"])],
        blank=True,
    )
    source_sha256 = models.CharField(max_length=64, blank=True)
    published_book_id = models.UUIDField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["work__author", "work__title", "language"]
        indexes = [
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["work", "language"]),
            models.Index(fields=["work", "status"]),
        ]

    def save(self, *args, **kwargs):
        # Only an original can root the tree. Correct the default rather than
        # trusting every creation path to pass the right role.
        if (
            self.edition_type != self.EditionType.ORIGINAL
            and self.parallel_role == self.ParallelRole.CANONICAL
        ):
            self.parallel_role = (
                self.ParallelRole.PARALLEL
                if self.edition_type == self.EditionType.MACHINE_TRANSLATION
                else self.ParallelRole.STANDALONE
            )
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} [{self.language}]"

    @property
    def is_canonical(self) -> bool:
        return self.parallel_role == self.ParallelRole.CANONICAL

    @property
    def supports_parallel_reading(self) -> bool:
        """True when this edition shares canonical block groups with its tree."""

        return self.parallel_role in {self.ParallelRole.CANONICAL, self.ParallelRole.PARALLEL}

    @property
    def requires_inferred_alignment(self) -> bool:
        """True when block correspondence has to be guessed rather than inherited.

        A canonical or generated parallel edition shares block groups with its
        tree, so its correspondence is exact by construction and inference would
        only replace certainty with a confidence score.
        """

        return self.source_edition_id is not None and not self.supports_parallel_reading

    @property
    def is_machine_generated(self) -> bool:
        return self.edition_type in {
            self.EditionType.MACHINE_TRANSLATION,
            self.EditionType.ADAPTATION,
        }


class Chapter(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="chapters", on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()
    title = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["edition", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "sequence"],
                name="catalog_chapter_edition_sequence_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.edition}: chapter {self.sequence}"


class ContentBlock(TimestampedModel):
    class BlockType(models.TextChoices):
        PARAGRAPH = "paragraph", "Paragraph"
        HEADING = "heading", "Heading"
        VERSE_LINE = "verse_line", "Verse line"
        VERSE_STANZA = "verse_stanza", "Verse stanza"
        BLOCKQUOTE = "blockquote", "Block quote"
        LETTER = "letter", "Letter"
        EPIGRAPH = "epigraph", "Epigraph"
        DIALOGUE = "dialogue", "Dialogue"
        FOOTNOTE = "footnote", "Footnote"
        IMAGE = "image", "Image"
        SEPARATOR = "separator", "Separator"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="blocks", on_delete=models.CASCADE)
    chapter = models.ForeignKey(Chapter, related_name="blocks", on_delete=models.CASCADE)
    block_id = models.CharField(max_length=80)
    sequence = models.PositiveIntegerField()
    block_type = models.CharField(max_length=20, choices=BlockType.choices)
    text = models.TextField(blank=True)
    sentences = models.JSONField(default=list, blank=True)
    align_group = models.UUIDField(null=True, blank=True)
    source_ref = models.CharField(max_length=1000, blank=True)
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["edition", "chapter__sequence", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "block_id"],
                name="catalog_block_edition_block_id_unique",
            ),
            models.UniqueConstraint(
                fields=["chapter", "sequence"],
                name="catalog_block_chapter_sequence_unique",
            ),
        ]
        indexes = [
            models.Index(fields=["edition", "align_group"]),
            models.Index(fields=["align_group"], name="catalog_block_align_group_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.edition.slug}:{self.block_id}"


class BlockAlignment(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_edition = models.ForeignKey(
        Edition,
        related_name="source_alignments",
        on_delete=models.CASCADE,
    )
    target_edition = models.ForeignKey(
        Edition,
        related_name="target_alignments",
        on_delete=models.CASCADE,
    )
    source_block = models.ForeignKey(
        ContentBlock,
        related_name="outgoing_alignments",
        on_delete=models.CASCADE,
    )
    target_block = models.ForeignKey(
        ContentBlock,
        related_name="incoming_alignments",
        on_delete=models.CASCADE,
    )
    group_id = models.UUIDField(default=uuid.uuid4, editable=False)
    confidence = models.FloatField()
    strategy = models.CharField(max_length=80)

    class Meta:
        ordering = ["target_edition", "target_block__sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_edition", "target_edition", "source_block", "target_block"],
                name="catalog_alignment_block_pair_unique",
            )
        ]
        indexes = [models.Index(fields=["source_edition", "target_edition", "confidence"])]


class ChapterAlignment(TimestampedModel):
    """A persisted many-to-many chapter correspondence group."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_edition = models.ForeignKey(
        Edition,
        related_name="source_chapter_alignments",
        on_delete=models.CASCADE,
    )
    target_edition = models.ForeignKey(
        Edition,
        related_name="target_chapter_alignments",
        on_delete=models.CASCADE,
    )
    source_chapter = models.ForeignKey(
        Chapter,
        related_name="outgoing_alignments",
        on_delete=models.CASCADE,
    )
    target_chapter = models.ForeignKey(
        Chapter,
        related_name="incoming_alignments",
        on_delete=models.CASCADE,
    )
    group_id = models.UUIDField(default=uuid.uuid4, editable=False)
    confidence = models.FloatField()
    strategy = models.CharField(max_length=80)

    class Meta:
        ordering = ["target_edition", "target_chapter__sequence", "source_chapter__sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "source_edition",
                    "target_edition",
                    "source_chapter",
                    "target_chapter",
                ],
                name="catalog_alignment_chapter_pair_unique",
            )
        ]
        indexes = [models.Index(fields=["source_edition", "target_edition", "confidence"])]


class AlignmentGroupReview(TimestampedModel):
    class Decision(models.TextChoices):
        ACCEPTED = "accepted", "Accepted"
        REPAIRED = "repaired", "Manually repaired"
        AI_ACCEPTED = "ai_accepted", "AI accepted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    target_edition = models.ForeignKey(
        Edition,
        related_name="alignment_group_reviews",
        on_delete=models.CASCADE,
    )
    group_id = models.UUIDField()
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="alignment_group_reviews",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    source_block_ids = models.JSONField(default=list)
    target_block_ids = models.JSONField(default=list)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["target_edition", "group_id"],
                name="catalog_alignment_review_edition_group_unique",
            )
        ]


class ContentBlockRevision(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(
        Edition,
        related_name="block_revisions",
        on_delete=models.CASCADE,
    )
    block = models.ForeignKey(
        ContentBlock,
        related_name="revisions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    stable_block_id = models.CharField(max_length=80)
    editor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="book_block_revisions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    previous_text = models.TextField()
    revised_text = models.TextField()
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


# The bibliographic fields the metadata stage decides, in the wording the
# processing history and the review panel use for them.
METADATA_FIELD_LABELS = {
    "title": "title",
    "author": "author",
    "description": "blurb",
    "language": "language",
    "publication_year": "first-published year",
}

METADATA_PROVENANCE_PHRASES = {
    "ai": "AI proposed",
    "source": "file header supplied",
    "user": "editor pinned",
}


class PipelineRun(TimestampedModel):
    class Stage(models.TextChoices):
        INGEST = "ingest", "Source ingestion"
        METADATA = "metadata", "Metadata detection"
        SENTENCES = "sentences", "Sentence splitting"
        ALIGN = "align", "Alignment"
        LEXICAL = "lexical", "Lexical analysis"
        SOURCE_QA = "source_qa", "Source text QA"
        TRANSLATE = "translate", "Translation"
        ADAPT = "adapt", "Level adaptation"
        PUBLISH = "publish", "Publication"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="pipeline_runs", on_delete=models.CASCADE)
    stage = models.CharField(max_length=20, choices=Stage.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    idempotency_key = models.CharField(max_length=255, unique=True)
    processor_version = models.CharField(max_length=40)
    input_hash = models.CharField(max_length=64)
    progress = models.PositiveSmallIntegerField(default=0)
    confidence = models.FloatField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]

    @property
    def summary_note(self) -> str:
        """One line saying what this run decided, for the processing history.

        Only the metadata stage has something to say so far: whose decision each
        bibliographic field is, so a reader of the history can see that a model
        named the book rather than the file header.
        """

        if self.stage != self.Stage.METADATA or not self.summary:
            return ""
        provenance = self.summary.get("provenance") or {}
        by_source: dict[str, list[str]] = {}
        for name, label in METADATA_FIELD_LABELS.items():
            source = provenance.get(name)
            if source in METADATA_PROVENANCE_PHRASES:
                by_source.setdefault(source, []).append(label)
        parts = [
            f"{phrase} {', '.join(by_source[source])}"
            for source, phrase in METADATA_PROVENANCE_PHRASES.items()
            if source in by_source
        ]
        if not self.summary.get("ai_enabled"):
            parts.append("no model configured")
        elif not self.summary.get("open_fields"):
            parts.append("every field was pinned, so no model was called")
        elif self.summary.get("ai_status") != AIRun.Status.SUCCEEDED:
            parts.append("the model call did not complete")
        return " · ".join(parts) or "nothing detected"


class EditionArtifact(TimestampedModel):
    """A reusable, versioned result derived from one normalized edition."""

    class Kind(models.TextChoices):
        LEXICAL_PROFILE = "lexical_profile", "Lexical profile"
        USEFUL_WORDS = "useful_words", "Useful words"
        SOURCE_QA = "source_qa", "Source text QA"
        DIFFICULTY = "difficulty", "Difficulty assessment"
        DESCRIPTION = "description", "Generated description"
        CHAPTER_SUMMARY = "chapter_summary", "Chapter summary"
        QUIZ = "quiz", "Quiz"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="artifacts", on_delete=models.CASCADE)
    pipeline_run = models.ForeignKey(
        PipelineRun,
        related_name="artifacts",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=40, choices=Kind.choices)
    schema_version = models.PositiveSmallIntegerField(default=1)
    input_hash = models.CharField(max_length=64)
    processor_version = models.CharField(max_length=80)
    payload = models.JSONField(default=dict)
    is_current = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "kind", "input_hash", "processor_version"],
                name="catalog_artifact_edition_kind_input_processor_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["edition", "kind", "created_at"],
                name="catalog_art_edition_kind_idx",
            )
        ]


class TextQualityFinding(TimestampedModel):
    """One reviewable source-text anomaly; it never mutates text autonomously."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        APPLIED = "applied", "Correction applied"
        DISMISSED = "dismissed", "Dismissed"
        SUPERSEDED = "superseded", "Superseded by a text revision"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(
        Edition,
        related_name="text_quality_findings",
        on_delete=models.CASCADE,
    )
    pipeline_run = models.ForeignKey(
        PipelineRun,
        related_name="text_quality_findings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    artifact = models.ForeignKey(
        EditionArtifact,
        related_name="text_quality_findings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    block = models.ForeignKey(
        ContentBlock,
        related_name="text_quality_findings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    stable_block_id = models.CharField(max_length=80, blank=True)
    input_hash = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    code = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    start_offset = models.PositiveIntegerField(null=True, blank=True)
    end_offset = models.PositiveIntegerField(null=True, blank=True)
    original_text = models.TextField(blank=True)
    suggested_text = models.TextField(blank=True)
    confidence = models.FloatField()
    message = models.TextField()
    evidence = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reviewed_text_quality_findings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    @property
    def can_apply(self) -> bool:
        return (
            self.status == self.Status.OPEN
            and self.block_id is not None
            and self.start_offset is not None
            and self.end_offset is not None
        )

    class Meta:
        ordering = ["status", "-confidence", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "input_hash", "fingerprint"],
                name="catalog_text_finding_input_fingerprint_unique",
            )
        ]
        indexes = [
            models.Index(
                fields=["edition", "status", "created_at"],
                name="catalog_text_ed_status_idx",
            )
        ]


class QAWarning(TimestampedModel):
    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="warnings", on_delete=models.CASCADE)
    pipeline_run = models.ForeignKey(
        PipelineRun,
        related_name="warnings",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    block = models.ForeignKey(
        ContentBlock,
        related_name="warnings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    code = models.CharField(max_length=100)
    severity = models.CharField(max_length=10, choices=Severity.choices, default=Severity.WARNING)
    message = models.TextField()
    source_ref = models.CharField(max_length=1000, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="resolved_book_warnings",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["resolved_at", "-created_at"]
        indexes = [models.Index(fields=["edition", "resolved_at"])]


class ReviewDecision(TimestampedModel):
    """An operator's decision that an imported edition is ready to proceed.

    Decisions are tied to the source hash so a later re-import cannot appear to
    have been reviewed merely because an earlier version was approved.
    """

    class Decision(models.TextChoices):
        COMPLETE = "complete", "Review completed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="review_decisions", on_delete=models.CASCADE)
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="book_review_decisions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    decision = models.CharField(max_length=20, choices=Decision.choices, default=Decision.COMPLETE)
    notes = models.TextField(blank=True)
    source_sha256 = models.CharField(max_length=64, blank=True)
    actionable_warning_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class ModelConfiguration(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=120)
    purpose = models.CharField(max_length=50)
    parameters = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.name}: {self.provider}/{self.model}"


class PromptTemplate(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    purpose = models.CharField(max_length=50)
    system_prompt = models.TextField()
    user_template = models.TextField()
    output_schema = models.JSONField(default=dict)
    active = models.BooleanField(default=False)

    class Meta:
        ordering = ["name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "version"],
                name="catalog_prompt_name_version_unique",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} v{self.version}"


class AIRun(TimestampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SUBMITTED = "submitted", "Submitted"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="ai_runs", on_delete=models.CASCADE)
    pipeline_run = models.ForeignKey(
        PipelineRun,
        related_name="ai_runs",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    model_configuration = models.ForeignKey(ModelConfiguration, on_delete=models.PROTECT)
    prompt_template = models.ForeignKey(PromptTemplate, on_delete=models.PROTECT)
    idempotency_key = models.CharField(max_length=255, unique=True, null=True, blank=True)
    input_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    provider_request_id = models.CharField(max_length=255, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    cached_input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    reasoning_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    request_payload = models.JSONField(default=dict)
    response_payload = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class UserErrorReport(TimestampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    edition = models.ForeignKey(Edition, related_name="error_reports", on_delete=models.CASCADE)
    block = models.ForeignKey(
        ContentBlock,
        related_name="error_reports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reporter_user_id = models.UUIDField(null=True, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["status", "-created_at"]
