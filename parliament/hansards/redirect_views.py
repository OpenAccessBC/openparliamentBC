import datetime

from django.http import HttpRequest, HttpResponse, Http404, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404

from parliament.hansards.models import Document, OldSequenceMapping


def hansard_redirect(
        request: HttpRequest,
        hansard_id: str | None = None,
        hansard_date: str | None = None,
        sequence: str | None = None,
        only: str | None = None) -> HttpResponse:

    if not (hansard_id or hansard_date):
        raise Http404

    if hansard_id:
        doc = get_object_or_404(Document.debates, pk=hansard_id)
    else:
        doc = get_object_or_404(Document.debates, date=datetime.date(*[int(x) for x in hansard_date.split('-')]))

    url = doc.get_absolute_url()
    assert url is not None

    if sequence:
        try:
            seq_mapping = OldSequenceMapping.objects.get(document=doc, sequence=sequence)
            sequence = seq_mapping.slug
        except OldSequenceMapping.DoesNotExist:
            pass
        url += '%s/' % sequence

    if only:
        url += 'only/'

    return HttpResponsePermanentRedirect(url)
