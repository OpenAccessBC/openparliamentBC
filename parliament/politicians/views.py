import datetime
import itertools
import re
from collections.abc import Generator
from typing import Any, Callable, override
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.core.exceptions import PermissionDenied
from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.db.models import QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404
from django.template import loader
from django.urls import reverse
from django.views.decorators.vary import vary_on_headers

from parliament.activity import utils as activity
from parliament.activity.models import Activity
from parliament.core.api import APIFilters, ModelDetailView, ModelListView
from parliament.core.models import ElectedMember, Politician
from parliament.core.utils import feed_wrapper, is_ajax
from parliament.hansards.models import Document, Statement
from parliament.text_analysis.models import TextAnalysis
from parliament.text_analysis.views import TextAnalysisView
from parliament.utils.views import JSONView


class CurrentMPView(ModelListView):

    resource_name = 'Politicians'

    default_limit = 338

    # The API stuff here is a bit of a hack: because of the database schema, it makes sense
    # to internally use ElectedMembers in order to add more fields to the default response,
    # but for former politicians we use Politician objects, so... hacking.
    @staticmethod
    def _politician_prepend_filter(field_name: str, help_txt: str) -> Callable:
        def inner(qs: QuerySet[Politician], *args: Any, **kwargs: Any) -> QuerySet[Politician]:
            if qs.model == Politician:
                return APIFilters.dbfield(field_name)(qs, *args, **kwargs)

            return APIFilters.dbfield('politician__' + field_name)(qs, *args, **kwargs)

        setattr(inner, "help", help_txt)
        return inner

    filters = {
        'name': _politician_prepend_filter('name', help_txt='e.g. Stephen Harper'),
        'family_name': _politician_prepend_filter('name_family', help_txt='e.g. Harper'),
        'given_name': _politician_prepend_filter('name_given', help_txt='e.g. Stephen'),
        'include': APIFilters.noop(help_txt="'former' to show former MPs (since 94), 'all' for current and former")
    }

    @override
    def get_qs(self, request: HttpRequest | None = None, **kwargs: Any) -> QuerySet[Politician] | QuerySet[ElectedMember]:
        if request and request.GET.get('include') == 'former':
            return Politician.objects.elected_but_not_current().order_by('name_family')

        if request and request.GET.get('include') == 'all':
            return Politician.objects.elected().order_by('name_family')

        return ElectedMember.objects.current().order_by(
            'riding__province', 'politician__name_family').select_related('politician', 'riding', 'party')

    @override
    def object_to_dict(self, obj: Any) -> dict[str, Any]:
        if isinstance(obj, ElectedMember):
            return {
                "name": obj.politician.name,
                "url": obj.politician.get_absolute_url(),
                "current_party": {"short_name": {"en": obj.party.short_name}},
                "current_riding": {"province": obj.riding.province, "name": {"en": obj.riding.dashed_name}},
                "image": obj.politician.headshot.url if obj.politician.headshot else None,
            }

        return super(CurrentMPView, self).object_to_dict(obj)

    def get_html(self, request: HttpRequest) -> HttpResponse:
        t = loader.get_template('politicians/electedmember_list.html')
        c = {
            'object_list': self.get_qs(),
            'title': 'Current Members of Parliament'
        }
        return HttpResponse(t.render(c, request))


current_mps = CurrentMPView.as_view()


class FormerMPView(ModelListView):

    resource_name = 'Politicians'

    @override
    def get_json(self, request: HttpRequest, **kwargs: Any) -> HttpResponse:
        return HttpResponsePermanentRedirect(reverse('politicians') + '?include=former')

    def get_html(self, request: HttpRequest) -> HttpResponse:
        former_members = ElectedMember.objects.exclude(end_date__isnull=True)\
            .order_by('riding__province', 'politician__name_family', '-start_date')\
            .select_related('politician', 'riding', 'party')
        seen = set(Politician.objects.current().values_list('id', flat=True))
        object_list = []
        for member in former_members:
            if member.politician_id not in seen:
                object_list.append(member)
                seen.add(member.politician_id)

        c = {
            'object_list': object_list,
            'title': 'Former MPs (since 1994)'
        }
        t = loader.get_template("politicians/former_electedmember_list.html")
        return HttpResponse(t.render(c, request))


former_mps = FormerMPView.as_view()


class PoliticianView(ModelDetailView):

    resource_name = 'Politician'

    api_notes = """The other_info field is a direct copy of an internal catchall key-value store;
        beware that its structure may change frequently."""

    def get_object(self, request: HttpRequest, pol_id: str | None = None, pol_slug: str | None = None) -> Politician:
        if pol_slug:
            return get_object_or_404(Politician, slug=pol_slug)

        return get_object_or_404(Politician, pk=pol_id)

    @override
    def get_related_resources(self, request: HttpRequest, obj: Politician, result: dict[str, str]) -> dict[str, str]:
        pol_query = '?' + urlencode({'politician': obj.identifier})
        return {
            'speeches_url': reverse('speeches') + pol_query,
            'ballots_url': reverse('vote_ballots') + pol_query,
            'sponsored_bills_url': reverse('bills') + '?' + urlencode({'sponsor_politician': obj.identifier}),
            'activity_rss_url': reverse('politician_activity_feed', kwargs={'pol_id': obj.id})
        }

    def get_html(self, request: HttpRequest, pol_id: str | None = None, pol_slug: str | None = None) -> HttpResponse:
        pol: Politician = self.get_object(request, pol_id, pol_slug)
        if pol.slug and not pol_slug:
            return HttpResponsePermanentRedirect(pol.get_absolute_url())

        show_statements = bool('page' in request.GET or (pol.latest_member and not pol.latest_member.current))

        if show_statements:
            STATEMENTS_PER_PAGE = 10
            statements = pol.statement_set.filter(
                procedural=False, document__document_type=Document.DEBATE).order_by('-time', '-sequence')
            paginator = Paginator(statements, STATEMENTS_PER_PAGE)
            try:
                pagenum = int(request.GET.get('page', '1'))
            except ValueError:
                pagenum = 1
            try:
                statement_page = paginator.page(pagenum)
            except (EmptyPage, InvalidPage):
                statement_page = paginator.page(paginator.num_pages)
        else:
            statement_page = None

        c = {
            'pol': pol,
            'member': pol.latest_member,
            'candidacies': pol.candidacy_set.all().order_by('-election__date'),
            'electedmembers': pol.electedmember_set.all().order_by('-start_date'),
            'page': statement_page,
            'statements_politician_view': True,
            'show_statements': show_statements,
            'activities': activity.iter_recent(Activity.public.filter(politician=pol)),
            'search_placeholder': "Search %s in Parliament" % pol.name,
            'wordcloud_js': TextAnalysis.objects.get_wordcloud_js(
                key=pol.get_absolute_url() + 'text-analysis/')
        }
        if is_ajax(request):
            t = loader.get_template("hansards/statement_page_politician_view.inc")
        else:
            t = loader.get_template("politicians/politician.html")
        return HttpResponse(t.render(c, request))


politician = vary_on_headers('X-Requested-With')(PoliticianView.as_view())


def contact(request: HttpRequest, pol_id: str | None = None, pol_slug: str | None = None) -> HttpResponse:
    if pol_slug:
        pol = get_object_or_404(Politician, slug=pol_slug)
    else:
        pol = get_object_or_404(Politician, pk=pol_id)

    if not pol.current_member:
        raise Http404

    c = {
        'pol': pol,
        'info': pol.info(),
        'title': 'Contact %s' % pol.name
    }
    t = loader.get_template("politicians/contact.html")
    return HttpResponse(t.render(c, request))


def hide_activity(request: HttpRequest) -> HttpResponse:
    if not request.user.is_authenticated and request.user.is_staff:
        raise PermissionDenied

    activity = Activity.objects.get(pk=request.POST['activity_id'])
    activity.active = False
    activity.save()
    return HttpResponse('OK')


class PoliticianAutocompleteView(JSONView):

    def get(self, request: HttpRequest) -> list[dict[str, str]]:

        q = request.GET.get('q', '').lower()

        if not hasattr(self, 'politician_list'):
            self.politician_list: list[dict[str, str | int | None]] = list(Politician.objects.elected().values(
                'name', 'name_family', 'slug', 'id').order_by('name_family'))

        results = (
            {'value': str(p["slug"]) if p["slug"] else str(p["id"]), 'label': str(p["name"])}
            for p in self.politician_list
            if p["name"].lower().startswith(q) or p["name_family"].lower().startswith(q)
        )
        return list(itertools.islice(results, 15))


politician_autocomplete = PoliticianAutocompleteView.as_view()


class PoliticianMembershipView(ModelDetailView):

    resource_name = 'Politician membership'

    def get_object(self, request: HttpRequest, member_id: str) -> ElectedMember:
        return ElectedMember.objects.select_related('party', 'riding', 'politician').get(id=member_id)


class PoliticianMembershipListView(ModelListView):

    resource_name = 'Politician memberships'

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[ElectedMember]:
        return ElectedMember.objects.all().select_related('party', 'riding', 'politician')


class PoliticianStatementFeed(Feed[Statement, Politician]):
    @override
    def get_object(self, request: HttpRequest, pol_id: str) -> Politician:
        self.language = request.GET.get('language', settings.LANGUAGE_CODE)
        return get_object_or_404(Politician, pk=pol_id)

    @override
    def title(self, pol: Politician) -> str:
        return "%s in the House of Commons" % pol.name

    @override
    def link(self, pol: Politician) -> str:
        return "http://openparliament.ca" + pol.get_absolute_url()

    @override
    def description(self, pol: Politician) -> str:
        return "Statements by %s in the House of Commons, from openparliament.ca." % pol.name

    @override
    def items(self, pol: Politician) -> QuerySet[Statement]:
        return Statement.objects.filter(
            member__politician=pol, document__document_type=Document.DEBATE).order_by('-time')[:12]

    @override
    def item_title(self, item: Statement) -> str:
        return item.topic

    @override
    def item_link(self, item: Statement) -> str:
        return item.get_absolute_url()

    @override
    def item_description(self, item: Statement) -> str:
        assert self.language is not None
        return item.text_html(language=self.language)

    @override
    def item_pubdate(self, item: Statement) -> datetime.datetime:
        return item.time


politician_statement_feed = feed_wrapper(PoliticianStatementFeed)

r_title = re.compile(r'<span class="tag.+?>(.+?)</span>')
r_link = re.compile(r'<a [^>]*?href="(.+?)"')
r_excerpt = re.compile(r'<span class="excerpt">')


class PoliticianActivityFeed(Feed[Activity, Politician]):

    @override
    def get_object(self, request: HttpRequest, pol_id: str) -> Politician:
        return get_object_or_404(Politician, pk=pol_id)

    @override
    def title(self, pol: Politician) -> str:
        return pol.name

    @override
    def link(self, pol: Politician) -> str:
        return "http://openparliament.ca" + pol.get_absolute_url()

    @override
    def description(self, pol: Politician) -> str:
        return "Recent news about %s, from openparliament.ca." % pol.name

    @override
    def items(self, pol: Politician) -> Generator[Activity]:
        return activity.iter_recent(Activity.objects.filter(politician=pol))

    @override
    def item_title(self, item: Activity) -> str:
        # FIXME wrap in try
        return r_title.search(item.payload).group(1)

    @override
    def item_link(self, item: Activity) -> str:
        match = r_link.search(item.payload)
        if match:
            return match.group(1)

        # FIXME include links in activity model?
        return ''

    @override
    def item_guid(self, activity: Activity) -> str:
        return activity.guid

    @override
    def item_description(self, item: Activity) -> str:
        payload = r_excerpt.sub(
            ('<br><span style="display: block; border-left: 1px dotted #AAAAAA; margin-left: 2em; '
             'padding-left: 1em; font-style: italic; margin-top: 5px;">'), item.payload_wrapped())
        payload = r_title.sub('', payload)
        return payload

    @override
    def item_pubdate(self, item: Activity) -> datetime.datetime:
        return datetime.datetime(item.date.year, item.date.month, item.date.day)


class PoliticianTextAnalysisView(TextAnalysisView):

    expiry_days = 14

    @override
    def get_qs(self, request: HttpRequest, pol_id: str | None = None, pol_slug: str | None = None, **kwargs: Any) -> QuerySet[Statement]:
        if pol_slug:
            pol = get_object_or_404(Politician, slug=pol_slug)
        else:
            pol = get_object_or_404(Politician, pk=pol_id)
        request.pol = pol
        return pol.get_text_analysis_qs()

    @override
    def get_analysis(self, request: HttpRequest, **kwargs: Any) -> TextAnalysis:
        analysis = super(PoliticianTextAnalysisView, self).get_analysis(request, **kwargs)
        word = analysis.top_word
        if word and word != request.pol.info().get('favourite_word'):
            request.pol.set_info('favourite_word', word)
        return analysis


analysis = PoliticianTextAnalysisView.as_view()
