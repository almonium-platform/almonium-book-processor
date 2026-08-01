from __future__ import annotations

from django import forms

from almonium_book_processor.catalog.models import Edition
from almonium_book_processor.catalog.services import create_source_edition
from almonium_book_processor.ingest.source import SUPPORTED_SOURCE_EXTENSIONS


class EditionUploadForm(forms.Form):
    source_file = forms.FileField(
        validators=[],
        widget=forms.ClearableFileInput(attrs={"accept": ".epub,.xml", "data-drop-input": "true"}),
    )
    work_slug = forms.SlugField(max_length=160)
    work_title = forms.CharField(max_length=500)
    author = forms.CharField(max_length=300)
    original_language = forms.CharField(max_length=35)
    edition_slug = forms.SlugField(max_length=180)
    edition_title = forms.CharField(max_length=500)
    language = forms.CharField(max_length=35)
    edition_type = forms.ChoiceField(choices=Edition.EditionType.choices)

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
