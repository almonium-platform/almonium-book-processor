from __future__ import annotations

from django import forms

from almonium_book_processor.catalog.ai_translation import REGISTER_CHOICES
from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.services import create_source_edition
from almonium_book_processor.ingest.source import SUPPORTED_SOURCE_EXTENSIONS
from almonium_book_processor.languages import LANGUAGE_CHOICES


class EditionUploadForm(forms.Form):
    source_file = forms.FileField(
        validators=[],
        widget=forms.ClearableFileInput(attrs={"accept": ".epub,.xml", "data-drop-input": "true"}),
    )
    work_slug = forms.SlugField(
        max_length=160,
        help_text="The stable slug for the work itself, for example pride-and-prejudice.",
        widget=forms.TextInput(attrs={"placeholder": "pride-and-prejudice"}),
    )
    work_title = forms.CharField(
        max_length=500,
        help_text="Work = the underlying literary work, for example Pride and Prejudice.",
        widget=forms.TextInput(attrs={"placeholder": "Pride and Prejudice"}),
    )
    author = forms.CharField(
        max_length=300,
        widget=forms.TextInput(attrs={"placeholder": "Jane Austen"}),
    )
    description = forms.CharField(
        widget=forms.Textarea(
            attrs={"placeholder": "A novel about Elizabeth Bennet and Mr Darcy."}
        ),
        required=False,
    )
    original_language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="Language of the original work, for example English (en).",
    )
    publication_year = forms.IntegerField(
        min_value=1,
        max_value=9999,
        help_text="Year the original work was first published, for example 1813.",
        widget=forms.NumberInput(attrs={"placeholder": "1813"}),
    )
    cover_url = forms.URLField(
        max_length=1000,
        required=False,
        assume_scheme="https",
        help_text="Optional public-domain cover URL; a typographic cover is used otherwise.",
        widget=forms.URLInput(
            attrs={"placeholder": "https://example.org/pride-and-prejudice-cover.jpg"}
        ),
    )
    edition_slug = forms.SlugField(
        max_length=180,
        help_text=(
            "Unique slug for this uploaded version, for example pride-and-prejudice-en-original."
        ),
        widget=forms.TextInput(attrs={"placeholder": "pride-and-prejudice-en-original"}),
    )
    edition_title = forms.CharField(
        max_length=500,
        help_text="Edition = this specific uploaded text/version; usually Pride and Prejudice.",
        widget=forms.TextInput(attrs={"placeholder": "Pride and Prejudice"}),
    )
    language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="Language of this uploaded edition, for example English (en).",
    )
    edition_type = forms.ChoiceField(
        choices=Edition.EditionType.choices,
        help_text="Original for the source text; otherwise choose the kind of derived version.",
    )
    source_edition = forms.ModelChoiceField(
        queryset=Edition.objects.filter(work__visibility="public").select_related("work"),
        required=False,
        help_text="Required for a translation, adaptation, or abridgement that should be aligned.",
    )
    cefr_level = forms.ChoiceField(
        choices=Edition.CEFRLevel.choices,
        help_text="Current editorial estimate; AI estimation can replace it later.",
    )

    def clean_source_file(self):
        source = self.cleaned_data["source_file"]
        if not any(
            source.name.lower().endswith(extension) for extension in SUPPORTED_SOURCE_EXTENSIONS
        ):
            raise forms.ValidationError("Only EPUB and TEI XML files are supported.")
        return source

    def clean(self):
        cleaned_data = super().clean()
        edition_type = cleaned_data.get("edition_type")
        source_edition = cleaned_data.get("source_edition")
        if edition_type and edition_type != Edition.EditionType.ORIGINAL and not source_edition:
            self.add_error("source_edition", "Select the edition this version derives from.")
        if edition_type == Edition.EditionType.ORIGINAL and source_edition:
            self.add_error(
                "source_edition",
                "An original edition cannot derive from another edition.",
            )
        if source_edition and source_edition.work.slug != cleaned_data.get("work_slug"):
            self.add_error("source_edition", "The source edition must belong to the same work.")
        return cleaned_data

    def save(self) -> Edition:
        return create_source_edition(**self.cleaned_data)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def clean(self, data, initial=None):
        clean_one = super().clean
        if isinstance(data, (list, tuple)):
            return [clean_one(item, initial) for item in data]
        return [clean_one(data, initial)]


class LegacyArtifactImportForm(forms.Form):
    artifacts = MultipleFileField(
        widget=MultipleFileInput(attrs={"accept": ".json", "data-drop-input": "true"})
    )


class ParallelTranslationForm(forms.Form):
    """Request a generated parallel edition from a canonical original."""

    target_language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        label="Translate into",
        help_text="A new parallel edition is created; the original is never modified.",
    )
    register = forms.ChoiceField(
        choices=REGISTER_CHOICES,
        initial="period-faithful",
        label="Literary register",
    )
    tier = forms.ChoiceField(
        choices=(
            ("quality", "Quality — best literary register (recommended)"),
            ("draft", "Draft — cheaper, for a throwaway sample"),
        ),
        initial="quality",
        label="Model tier",
    )
    mode = forms.ChoiceField(
        choices=(
            ("direct", "Direct — finishes in minutes, full price (recommended)"),
            ("batch", "Batch — half price, up to 24 hours"),
        ),
        initial="direct",
        label="Execution",
        help_text=(
            "Both produce identical text and the same block-for-block alignment. "
            "Batch halves the cost but depends on the provider's Batch service."
        ),
    )

    def __init__(self, *args, source_edition: Edition | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_edition = source_edition
        if source_edition is not None:
            self.fields["target_language"].choices = [
                (code, label) for code, label in LANGUAGE_CHOICES if code != source_edition.language
            ]

    def clean_target_language(self) -> str:
        language = self.cleaned_data["target_language"]
        if self.source_edition is None:
            return language
        if language == self.source_edition.language:
            raise forms.ValidationError("Choose a language other than the original.")
        return language
