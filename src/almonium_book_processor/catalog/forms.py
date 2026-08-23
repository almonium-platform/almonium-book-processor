from __future__ import annotations

from django import forms

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
