import json

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.template import loader
from django.views.decorators.cache import never_cache

from parliament.core.utils import is_ajax

from .models import Haiku


@never_cache
def haiku(request: HttpRequest, haiku_id: str | None = None) -> HttpResponse:

    if haiku_id:
        haikus = [get_object_or_404(Haiku, pk=haiku_id)]
    else:
        if is_ajax(request):
            haikus = list(Haiku.objects.filter(worthy=True).order_by('?')[:10])
        else:
            haikus = list(Haiku.objects.filter(worthy=True).order_by('?')[:1])

    if is_ajax(request):
        # time.sleep(2)
        return HttpResponse(
            json.dumps([[haiku.line1, haiku.line2, haiku.line3, haiku.attribution_url, haiku.attribution, haiku.id]
                        for haiku in haikus]),
            content_type="application/json")

    t = loader.get_template("haiku/haiku.html")
    c = {
        'haiku': haikus[0]
    }
    return HttpResponse(t.render(c, request))
