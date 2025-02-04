import datetime
from typing import Any, override
from urllib.parse import urlencode

from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import loader
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers
from django.views.generic.dates import ArchiveIndexView, MonthArchiveView, YearArchiveView

from parliament.committees.models import CommitteeMeeting
from parliament.core.api import APIFilters, BadRequest, ModelDetailView, ModelListView
from parliament.core.utils import is_ajax
from parliament.hansards.models import Document, Statement
from parliament.text_analysis.models import TextAnalysis
from parliament.text_analysis.views import TextAnalysisView


def _get_hansard(year: str, month: str, day: str) -> Document:
    try:
        return get_object_or_404(Document.debates, date=datetime.date(int(year), int(month), int(day)))
    except ValueError:
        raise Http404 from None


class HansardView(ModelDetailView):

    resource_name = 'House debate'

    def get_object(self, request: HttpRequest, **kwargs: Any) -> Document:
        return _get_hansard(**kwargs)

    def get_html(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        return document_view(request, _get_hansard(**kwargs))

    @override
    def get_related_resources(self, request: HttpRequest, obj: Document, result: dict[str, str]) -> dict[str, str]:
        return {
            'speeches_url': reverse('speeches') + '?' + urlencode({'document': result['url']}),
            'debates_url': reverse('debates')
        }


hansard = HansardView.as_view()


class HansardStatementView(ModelDetailView):

    resource_name = 'Speech (House debate)'

    def get_object(self, request: HttpRequest, year: str, month: str, day: str, slug: str) -> Statement:
        date = datetime.date(int(year), int(month), int(day))
        return Statement.objects.get(
            document__document_type='D',
            document__date=date,
            slug=slug
        )

    @override
    def get_related_resources(self, request: HttpRequest, obj: Statement, result: dict[str, str]) -> dict[str, str]:
        return {
            'document_speeches_url': reverse('speeches') + '?' + urlencode({'document': result['document_url']}),
        }

    def get_html(self, request: HttpRequest, year: str, month: str, day: str, slug: str) -> HttpResponse:
        return document_view(request, _get_hansard(year, month, day), slug=slug)


hansard_statement = HansardStatementView.as_view()


def document_redirect(request: HttpRequest, document_id: str, slug: str | None = None) -> HttpResponse:
    try:
        document: Document = Document.objects.select_related(
            'committeemeeting', 'committeemeeting__committee').get(pk=document_id)
    except Document.DoesNotExist:
        raise Http404 from None
    url: str | None = document.get_absolute_url()
    assert url is not None

    if slug:
        url += "%s/" % slug
    return HttpResponsePermanentRedirect(url)


@vary_on_headers('X-Requested-With')
def document_view(
        request: HttpRequest, document: Document, meeting: CommitteeMeeting | None = None, slug: str | None = None) -> HttpResponse:

    per_page: int = 25
    if 'singlepage' in request.GET:
        per_page = 50000

    statement_qs = Statement.objects.filter(document=document)\
        .select_related('member__politician', 'member__riding', 'member__party')
    paginator = Paginator(statement_qs, per_page)

    highlight_statement: int = 0
    try:
        if slug is not None and 'page' not in request.GET:
            if slug.isdigit():
                highlight_statement = int(slug)
            else:
                highlight_statement = statement_qs.filter(slug=slug).values_list('sequence', flat=True)[0]
            page = int(highlight_statement / per_page) + 1
        else:
            page = int(request.GET.get('page', '1'))
    except (ValueError, IndexError):
        page = 1

    # If page request (9999) is out of range, deliver last page of results.
    try:
        statements = paginator.page(page)
    except (EmptyPage, InvalidPage):
        statements = paginator.page(paginator.num_pages)

    if highlight_statement:
        try:
            highlight_statement = [s for s in statements.object_list if s.sequence == highlight_statement][0]
        except IndexError:
            raise Http404 from None

    ctx = {
        'document': document,
        'page': statements,
        'highlight_statement': highlight_statement,
        'singlepage': 'singlepage' in request.GET,
        'allow_single_page': True
    }
    if document.document_type == Document.DEBATE:
        ctx.update({
            'hansard': document,
            'pagination_url': document.get_absolute_url(),
        })
    elif document.document_type == Document.EVIDENCE:
        ctx.update({
            'meeting': meeting,
            'committee': meeting.committee,
            'pagination_url': meeting.get_absolute_url(),
        })

    if is_ajax(request):
        t = loader.get_template("hansards/statement_page.inc")
    else:
        if document.document_type == Document.DEBATE:
            t = loader.get_template("hansards/hansard_detail.html")
        elif document.document_type == Document.EVIDENCE:
            t = loader.get_template("committees/meeting_evidence.html")
        else:
            raise Http404

        ctx['wordcloud_js'] = TextAnalysis.objects.get_wordcloud_js(key=document.get_text_analysis_url())

    return HttpResponse(t.render(ctx, request))


class SpeechesView(ModelListView):

    @staticmethod
    def document_filter(qs: QuerySet, view: ModelListView, filter_name: str, filter_extra: str, val: str) -> QuerySet:
        u = val.strip('/').split('/')
        if len(u) < 4:
            raise BadRequest("Invalid document URL")

        if u[-4] == 'debates':
            # /debates/2013/2/15/
            try:
                date = datetime.date(int(u[-3]), int(u[-2]), int(u[-1]))
            except ValueError:
                raise BadRequest("Invalid document URL") from None

            return qs.filter(document__document_type='D', document__date=date).order_by('sequence')

        if u[-4] == 'committees':
            # /commmittees/national-defence/41-1/63/
            try:
                meeting = CommitteeMeeting.objects.get(
                    committee__slug=u[-3], session=u[-2], number=u[-1])
            except (ValueError, CommitteeMeeting.DoesNotExist):
                raise BadRequest("Invalid meeting URL") from None

            return qs.filter(document=meeting.evidence_id).order_by('sequence')

        raise BadRequest("Invalid document URL")

    setattr(document_filter, "help", "the URL of the debate or committee meeting")

    filters = {
        'procedural': APIFilters.dbfield(help_txt="is this a short, routine procedural speech? True or False"),
        'document': document_filter,
        'politician': APIFilters.politician(),
        'politician_membership': APIFilters.fkey(lambda u: {'member': u[-1]}),
        'time': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="e.g. time__range=2012-10-19 10:00,2012-10-19 11:00"),
        'mentioned_politician': APIFilters.politician('mentioned_politicians'),
        'mentioned_bill': APIFilters.fkey(lambda u: {
            'bills__billinsession__session': u[-2],
            'bills__number': u[-1]
        }, help_txt="e.g. /bills/41-1/C-14/")
    }

    resource_name = 'Speeches'

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[Statement]:
        qs = Statement.objects.all().prefetch_related('politician')
        if 'document' not in request.GET:
            qs = qs.order_by('-time')
        return qs


speeches = SpeechesView.as_view()


class DebatePermalinkView(ModelDetailView):

    def _get_objs(self, request: HttpRequest, slug: str, year: str, month: str, day: str) -> tuple[Document, Statement]:
        doc = _get_hansard(year, month, day)
        if slug.isdigit():
            statement = get_object_or_404(Statement, document=doc, sequence=slug)
        else:
            statement = get_object_or_404(Statement, document=doc, slug=slug)
        return doc, statement

    @override
    def get_json(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        url = self._get_objs(request, **kwargs)[1].get_absolute_url()
        return HttpResponseRedirect(url + '?' + request.GET.urlencode())

    def get_html(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        doc, statement = self._get_objs(request, **kwargs)
        return statement_permalink(request, doc, statement, "hansards/statement_permalink.html", hansard=doc)


debate_permalink = DebatePermalinkView.as_view()


def statement_permalink(request: HttpRequest, doc: Document, statement: Statement, template: str, **kwargs: Any) -> HttpResponse:
    """A page displaying only a single statement. Used as a non-JS permalink."""

    if statement.politician:
        who = statement.politician.name
    else:
        who = statement.who
    title = who

    if statement.topic:
        title += ' on %s' % statement.topic
    elif 'committee' in kwargs:
        title += ' at the ' + kwargs['committee'].title

    t = loader.get_template(template)
    ctx = {
        'title': title,
        'who': who,
        'page': {'object_list': [statement]},
        'doc': doc,
        'statement': statement,
        'statements_full_date': True,
        'statement_url': statement.get_absolute_url(),
        # 'statements_context_link': True
    }
    ctx.update(kwargs)
    return HttpResponse(t.render(ctx, request))


def document_cache(request: HttpRequest, document_id: str, language: str) -> HttpResponse:
    document = get_object_or_404(Document, pk=document_id)
    xmlfile = document.get_cached_xml(language)
    resp = HttpResponse(xmlfile.read(), content_type="text/xml")
    xmlfile.close()
    return resp


class TitleAdder():

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]:
        context = super(TitleAdder, self).get_context_data(**kwargs)
        context.update(title=self.page_title)
        return context


class APIArchiveView(ModelListView):

    resource_name = 'House debates'

    filters = {
        'session': APIFilters.dbfield(help_txt='e.g. 41-1'),
        'date': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt='e.g. date__range=2010-01-01,2010-09-01'),
        'number': APIFilters.dbfield(help_txt='each Hansard in a session is given a sequential #'),
    }

    def get_html(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        return self.get(request, **kwargs)

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet:
        return self.get_dated_items()[1]


class DebateIndexView(TitleAdder, ArchiveIndexView, APIArchiveView):
    queryset = Document.debates.all()
    date_field = 'date'
    template_name = "hansards/hansard_archive.html"
    page_title = 'The Debates of the House of Commons'


index = DebateIndexView.as_view()


class DebateYearArchive(TitleAdder, YearArchiveView, APIArchiveView):
    queryset = Document.debates.all().order_by('date')
    date_field = 'date'
    make_object_list = True
    template_name = "hansards/hansard_archive_year.html"

    def page_title(self) -> str:
        return 'Debates from %s' % self.get_year()


by_year = DebateYearArchive.as_view()


class DebateMonthArchive(TitleAdder, MonthArchiveView, APIArchiveView):
    queryset = Document.debates.all().order_by('date')
    date_field = 'date'
    make_object_list = True
    month_format = "%m"
    template_name = "hansards/hansard_archive_year.html"

    def page_title(self) -> str:
        return 'Debates from %s' % self.get_year()


by_month = DebateMonthArchive.as_view()


class HansardAnalysisView(TextAnalysisView):

    @override
    def get_corpus_name(self, request: HttpRequest, year: str | None = None, **kwargs: Any) -> str:
        assert year is not None
        # Use a special corpus for old debates
        if int(year) < (datetime.date.today().year - 1):
            return 'debates-%s' % year
        return 'debates'

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[Statement]:
        h = _get_hansard(**kwargs)
        request.hansard = h
        qs = h.statement_set.all()
        # if 'party' in request.GET:
        #     qs = qs.filter(member__party__slug=request.GET['party'])
        return qs

    @override
    def get_analysis(self, request: HttpRequest, **kwargs: Any) -> TextAnalysis:
        analysis = super(HansardAnalysisView, self).get_analysis(request, **kwargs)
        word = analysis.top_word
        if word and word != request.hansard.most_frequent_word:
            Document.objects.filter(id=request.hansard.id).update(most_frequent_word=word)
        return analysis


hansard_analysis = HansardAnalysisView.as_view()
