from django import forms
from django.contrib import admin

from almonium_book_processor.catalog.models import (
    AIRun,
    AlignmentGroupReview,
    BlockAlignment,
    Chapter,
    ContentBlock,
    ContentBlockRevision,
    Edition,
    ModelConfiguration,
    PipelineRun,
    PromptTemplate,
    QAWarning,
    ReviewDecision,
    UserErrorReport,
    Work,
)
from almonium_book_processor.catalog.tasks import (
    align_edition_to_source,
    split_edition_sentences,
)
from almonium_book_processor.languages import LANGUAGE_CHOICES


class WorkAdminForm(forms.ModelForm):
    original_language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="Select the ISO 639-1 language code used by the original work.",
    )

    class Meta:
        model = Work
        fields = "__all__"


class EditionAdminForm(forms.ModelForm):
    language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="Select the ISO 639-1 language code for this edition.",
    )

    class Meta:
        model = Edition
        fields = "__all__"


@admin.register(Work)
class WorkAdmin(admin.ModelAdmin):
    form = WorkAdminForm
    list_display = ("title", "author", "original_language", "updated_at")
    search_fields = ("title", "author", "slug")
    prepopulated_fields = {"slug": ("author", "title")}


class ChapterInline(admin.TabularInline):
    model = Chapter
    extra = 0
    fields = ("sequence", "title")
    show_change_link = True


@admin.register(Edition)
class EditionAdmin(admin.ModelAdmin):
    form = EditionAdminForm
    list_display = (
        "title",
        "language",
        "cefr_level",
        "edition_type",
        "status",
        "word_count",
        "updated_at",
    )
    list_filter = ("status", "edition_type", "language", "cefr_level")
    search_fields = ("title", "author", "slug", "work__title")
    readonly_fields = ("source_sha256", "word_count", "created_at", "updated_at")
    autocomplete_fields = ("work", "source_edition")
    inlines = (ChapterInline,)
    actions = ("queue_sentence_splitting", "queue_source_alignment")

    @admin.action(description="Queue sentence splitting")
    def queue_sentence_splitting(self, request, queryset):
        for edition_id in queryset.values_list("id", flat=True):
            split_edition_sentences.delay(str(edition_id))

    @admin.action(description="Queue alignment to source edition")
    def queue_source_alignment(self, request, queryset):
        for edition_id in queryset.exclude(source_edition=None).values_list("id", flat=True):
            align_edition_to_source.delay(str(edition_id))


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    list_display = ("edition", "sequence", "title")
    list_filter = ("edition__language",)
    search_fields = ("edition__title", "title")
    autocomplete_fields = ("edition",)


@admin.register(ContentBlock)
class ContentBlockAdmin(admin.ModelAdmin):
    list_display = ("block_id", "edition", "chapter", "block_type", "sequence")
    list_filter = ("block_type", "edition__language")
    search_fields = ("block_id", "text", "edition__title")
    autocomplete_fields = ("edition", "chapter")
    readonly_fields = ("block_id", "source_ref", "created_at", "updated_at")


@admin.register(PipelineRun)
class PipelineRunAdmin(admin.ModelAdmin):
    list_display = ("edition", "stage", "status", "progress", "created_at")
    list_filter = ("stage", "status")
    search_fields = ("edition__title", "idempotency_key", "error")
    readonly_fields = ("idempotency_key", "input_hash", "created_at", "updated_at")


@admin.register(QAWarning)
class QAWarningAdmin(admin.ModelAdmin):
    list_display = ("code", "edition", "severity", "resolved_at", "created_at")
    list_filter = ("severity", "code", "resolved_at")
    search_fields = ("message", "edition__title", "source_ref")


@admin.register(ReviewDecision)
class ReviewDecisionAdmin(admin.ModelAdmin):
    list_display = ("edition", "reviewer", "decision", "actionable_warning_count", "created_at")
    list_filter = ("decision",)
    search_fields = ("edition__title", "reviewer__username", "notes")
    readonly_fields = (
        "edition",
        "reviewer",
        "decision",
        "notes",
        "source_sha256",
        "actionable_warning_count",
        "created_at",
        "updated_at",
    )


admin.site.register(ModelConfiguration)
admin.site.register(PromptTemplate)
admin.site.register(AIRun)
admin.site.register(UserErrorReport)
admin.site.register(BlockAlignment)
admin.site.register(AlignmentGroupReview)
admin.site.register(ContentBlockRevision)
