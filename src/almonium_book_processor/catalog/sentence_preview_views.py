from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from almonium_book_processor.catalog.models import Edition, Work
from almonium_book_processor.catalog.parallel_content import inherited_payload


@staff_member_required
def sentence_preview(request, edition_id, other_id):
    editions = Edition.objects.filter(work__visibility=Work.Visibility.PUBLIC)
    primary = get_object_or_404(editions, pk=edition_id)
    secondary = get_object_or_404(editions, pk=other_id, work=primary.work)
    payload = inherited_payload(primary, secondary)
    if payload is None:
        raise Http404("No complete inherited pair")
    try:
        chapter = int(request.GET.get("chapter", 11))
    except ValueError:
        raise Http404("Invalid chapter") from None
    payload["blocks"] = [b for b in payload["blocks"] if b["chapter"] == chapter]
    return render(
        request,
        "catalog/sentence_preview.html",
        {
            "payload": payload,
            "primary": primary,
            "secondary": secondary,
        },
    )
