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
    work_slug = forms.SlugField(max_length=160)
    work_title = forms.CharField(max_length=500)
    author = forms.CharField(max_length=300)
    original_language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="ISO 639-1 language code for the original work.",
    )
    publication_year = forms.IntegerField(min_value=1, max_value=9999)
    cover_url = forms.URLField(
        max_length=1000,
        required=False,
        assume_scheme="https",
        help_text="Optional public-domain cover image URL. A typographic cover is used otherwise.",
    )
    edition_slug = forms.SlugField(max_length=180)
    edition_title = forms.CharField(max_length=500)
    language = forms.ChoiceField(
        choices=LANGUAGE_CHOICES,
        help_text="ISO 639-1 language code for this edition.",
    )
    edition_type = forms.ChoiceField(choices=Edition.EditionType.choices)
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
