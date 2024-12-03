from typing import Any, Optional

from django.conf import settings
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse
from django.views.generic import View

from parliament.hansards.models import Statement
from parliament.text_analysis.models import TextAnalysis


class TextAnalysisView(View):
    """Returns JSON text analysis data. Subclasses must define get_qs."""

    corpus_name = 'default'
    expiry_days: Optional[int] = None

    def get(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        if not settings.PARLIAMENT_GENERATE_TEXT_ANALYSIS:
            raise Http404
        try:
            analysis = self.get_analysis(request, **kwargs)
        except IOError:
            raise Http404 from None
        return HttpResponse(analysis.probability_data_json, content_type='application/json')

    def get_key(self, request: HttpRequest, **kwargs: Any) -> str:
        return request.path

    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[Statement]:
        raise NotImplementedError

    def get_corpus_name(self, request: HttpRequest, **kwargs: Any) -> str:
        return self.corpus_name

    def get_analysis(self, request: HttpRequest, **kwargs: Any) -> TextAnalysis:
        return TextAnalysis.objects.get_or_create_from_statements(
            key=self.get_key(request, **kwargs),
            qs=self.get_qs(request, **kwargs),
            corpus_name=self.get_corpus_name(request, **kwargs),
            expiry_days=self.expiry_days
        )
