import datetime
from typing import Any, Dict, List, override
from urllib.parse import urlencode

from django.contrib.syndication.views import Feed
from django.core.paginator import EmptyPage, InvalidPage, Paginator
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template import loader
from django.template.defaultfilters import date as format_date
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.views.decorators.vary import vary_on_headers

from parliament.bills.models import Bill, BillInSession, MemberVote, VoteQuestion
from parliament.core.api import APIFilters, ModelDetailView, ModelListView
from parliament.core.models import Session
from parliament.core.utils import is_ajax
from parliament.hansards.models import Statement


def bill_pk_redirect(request: HttpRequest, bill_id: int) -> HttpResponse:
    bill: Bill = get_object_or_404(Bill, pk=bill_id)
    return HttpResponsePermanentRedirect(
        reverse('bill', kwargs={'session_id': bill.get_session().id, 'bill_number': bill.number}))


class BillDetailView(ModelDetailView):

    resource_name = 'Bill'

    def get_object(self, request: HttpRequest, session_id: str, bill_number: str) -> BillInSession:
        return BillInSession.objects.select_related(
            'bill', 'sponsor_politician').get(session=session_id, bill__number=bill_number)

    @override
    def get_related_resources(self, request: HttpRequest, obj: BillInSession, result: Dict[str, str]) -> Dict[str, str]:
        return {
            'bills_url': reverse('bills')
        }

    def _render_page(self, request: HttpRequest, qs, per_page: int = 10):
        paginator = Paginator(qs, per_page)

        try:
            pagenum = int(request.GET.get('page', '1'))
        except ValueError:
            pagenum = 1
        try:
            return paginator.page(pagenum)
        except (EmptyPage, InvalidPage):
            return paginator.page(paginator.num_pages)

    def get_html(self, request: HttpRequest, session_id: str, bill_number: str) -> HttpResponse:
        bill = get_object_or_404(Bill, sessions=session_id, number=bill_number)

        mentions = (bill.statement_set.all()
                    .order_by('-time', '-sequence')
                    .select_related('member', 'member__politician', 'member__riding', 'member__party'))
        major_speeches = (bill.get_second_reading_debate()
                          .order_by('-document__session', 'document__date', 'sequence')
                          .select_related('member', 'member__politician', 'member__riding', 'member__party'))
        meetings = bill.get_committee_meetings()

        tab = request.GET.get('tab', 'major-speeches')

        has_major_speeches = major_speeches.exists()
        has_mentions = has_major_speeches or mentions.exists()
        has_meetings = meetings.exists()

        if tab == 'major-speeches' and not has_major_speeches:
            tab = 'mentions'

        per_page = 500 if request.GET.get('singlepage') else 15

        if tab == 'mentions':
            page = self._render_page(request, mentions, per_page=per_page)
        elif tab == 'major-speeches':
            page = self._render_page(request, major_speeches, per_page=per_page)
        else:
            page = None

        c = {
            'bill': bill,
            'has_major_speeches': has_major_speeches,
            'has_mentions': has_mentions,
            'has_meetings': has_meetings,
            'committee_meetings': meetings,
            'votequestions': bill.votequestion_set.all().order_by('-date', '-number'),
            'page': page,
            'allow_single_page': True,
            'tab': tab,
            'title': ('Bill %s' % bill.number) + (' (Historical)' if bill.session.end else ''),
            'statements_full_date': True,
            'statements_context_link': True,
        }
        if is_ajax(request):
            if tab == 'meetings':
                t = loader.get_template("bills/related_meetings.inc")
            else:
                t = loader.get_template("hansards/statement_page.inc")
        else:
            t = loader.get_template("bills/bill_detail.html")
        return HttpResponse(t.render(c, request))


bill = vary_on_headers('X-Requested-With')(BillDetailView.as_view())


class BillListView(ModelListView):

    resource_name = 'Bills'

    filters = {
        'session': APIFilters.dbfield(help_txt="e.g. 41-1"),
        'introduced': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="date bill was introduced, e.g. introduced__gt=2010-01-01"),
        'legisinfo_id': APIFilters.dbfield(help_txt="integer ID assigned by Parliament's LEGISinfo"),
        'number': APIFilters.dbfield(
            'bill__number',
            help_txt="a string, not an integer: e.g. C-10"),
        'law': APIFilters.dbfield(
            'bill__law',
            help_txt="did it become law? True, False"),
        'private_member_bill': APIFilters.dbfield(
            'bill__privatemember',
            help_txt="is it a private member's bill? True, False"),
        'status_code': APIFilters.dbfield('bill__status_code'),
        'sponsor_politician': APIFilters.politician('sponsor_politician'),
        'sponsor_politician_membership': APIFilters.fkey(lambda u: {'sponsor_member': u[-1]}),
    }

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[BillInSession]:
        return BillInSession.objects.all().select_related('bill', 'sponsor_politician')

    def get_html(self, request: HttpRequest) -> HttpResponse:
        sessions = Session.objects.with_bills()
        len(sessions)  # evaluate it
        bills = Bill.objects.filter(sessions=sessions[0])
        votes = VoteQuestion.objects.select_related('bill').filter(session=sessions[0])[:6]

        t = loader.get_template('bills/index.html')
        c = {
            'object_list': bills,
            'session_list': sessions,
            'votes': votes,
            'session': sessions[0],
            'title': 'Bills & Votes',
            'recently_active': Bill.objects.recently_active()
        }

        return HttpResponse(t.render(c, request))


index = BillListView.as_view()


class BillSessionListView(ModelListView):

    @override
    def get_json(self, request: HttpRequest, session_id: str | None = None, **kwargs: Any) -> HttpResponse:
        return HttpResponseRedirect(reverse('bills') + '?' + urlencode({'session': session_id}))

    def get_html(self, request: HttpRequest, session_id: str) -> HttpResponse:
        session = get_object_or_404(Session, pk=session_id)
        bills = Bill.objects.filter(sessions=session)
        votes = VoteQuestion.objects.select_related('bill').filter(session=session)[:6]

        t = loader.get_template('bills/bill_list.html')
        c = {
            'object_list': bills,
            'session': session,
            'votes': votes,
            'title': 'Bills for the %s' % session
        }
        return HttpResponse(t.render(c, request))


bills_for_session = BillSessionListView.as_view()


class VoteListView(ModelListView):

    resource_name = 'Votes'

    api_notes = mark_safe("""<p>What we call votes are <b>divisions</b> in official Parliamentary lingo.
        We refer to an individual person's vote as a <a href="/votes/ballots/">ballot</a>.</p>
    """)

    filters = {
        'session': APIFilters.dbfield(help_txt="e.g. 41-1"),
        'yea_total': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="# votes for"),
        'nay_total': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="# votes against, e.g. nay_total__gt=10"),
        'paired_total': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="paired votes are an odd convention that seem to have stopped in 2011"),
        'date': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="date__gte=2011-01-01"),
        'number': APIFilters.dbfield(
            filter_types=APIFilters.numeric_filters,
            help_txt="every vote in a session has a sequential number"),
        'bill': APIFilters.fkey(lambda u: {
            'bill__sessions': u[-2],
            'bill__number': u[-1]
        }, help_txt="e.g. /bills/41-1/C-10/"),
        'result': APIFilters.choices('result', VoteQuestion)
    }

    @override
    def get_json(self, request: HttpRequest, session_id: str | None = None, **kwargs: Any) -> Dict[str, Any] | HttpResponse:
        if session_id:
            return HttpResponseRedirect(reverse('votes') + '?' + urlencode({'session': session_id}))
        return super(VoteListView, self).get_json(request, **kwargs)

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[VoteQuestion]:
        return VoteQuestion.objects.select_related('bill').order_by('-date', '-number')

    def get_html(self, request: HttpRequest, session_id: str | None = None) -> HttpResponse:
        if session_id:
            session = get_object_or_404(Session, pk=session_id)
        else:
            session = Session.objects.current()

        t = loader.get_template('bills/votequestion_list.html')
        c = {
            'object_list': self.get_qs(request).filter(session=session),
            'session': session,
            'title': 'Votes for the %s' % session
        }
        return HttpResponse(t.render(c, request))


votes_for_session = VoteListView.as_view()


def vote_pk_redirect(request: HttpRequest, vote_id: str) -> HttpResponse:
    vote = get_object_or_404(VoteQuestion, pk=vote_id)
    return HttpResponsePermanentRedirect(
        reverse('vote', kwargs={'session_id': vote.session_id, 'number': vote.number}))


class VoteDetailView(ModelDetailView):

    resource_name = 'Vote'

    api_notes = VoteListView.api_notes

    def get_object(self, request: HttpRequest, session_id: str, number: str) -> VoteQuestion:
        return get_object_or_404(VoteQuestion, session=session_id, number=number)

    @override
    def get_related_resources(self, request: HttpRequest, obj: VoteQuestion, result: Dict[str, str]) -> Dict[str, str]:
        return {
            'ballots_url': reverse('vote_ballots') + '?' + urlencode({'vote': result['url']}),
            'votes_url': reverse('votes')
        }

    def get_html(self, request: HttpRequest, session_id: str, number: str) -> HttpResponse:
        vote = self.get_object(request, session_id, number)
        membervotes = MemberVote.objects.filter(votequestion=vote)\
            .order_by('member__party', 'member__politician__name_family')\
            .select_related('member', 'member__party', 'member__politician')
        partyvotes = vote.partyvote_set.select_related('party').all()

        c = {
            'vote': vote,
            'membervotes': membervotes,
            'parties_y': [pv.party for pv in partyvotes if pv.vote == 'Y'],
            'parties_n': [pv.party for pv in partyvotes if pv.vote == 'N']
        }
        t = loader.get_template("bills/votequestion_detail.html")
        return HttpResponse(t.render(c, request))


vote = VoteDetailView.as_view()


class BallotListView(ModelListView):

    resource_name = 'Ballots'

    filters = {
        'vote': APIFilters.fkey(lambda u: {'votequestion__session': u[-2],
                                           'votequestion__number': u[-1]},
                                help_txt="e.g. /votes/41-1/472/"),
        'politician': APIFilters.politician(),
        'politician_membership': APIFilters.fkey(
            lambda u: {'member': u[-1]},
            help_txt="e.g. /politicians/roles/326/"),
        'ballot': APIFilters.choices('vote', MemberVote),
        'dissent': APIFilters.dbfield(
            'dissent',
            help_txt="does this look like a vote against party line? not reliable for research. True, False")
    }

    @override
    def get_qs(self, request: HttpRequest, **kwargs: Any) -> QuerySet[MemberVote]:
        return MemberVote.objects.all().select_related('votequestion').order_by('-votequestion__date', '-votequestion__number')

    @override
    def object_to_dict(self, obj):
        return obj.to_api_dict(representation='list')


ballots = BallotListView.as_view()


class BillListFeed(Feed):
    title = 'Bills in the House of Commons'
    description = 'New bills introduced to the House, from openparliament.ca.'
    link = "/bills/"

    @override
    def items(self) -> QuerySet[Bill]:
        return Bill.objects.filter(introduced__isnull=False).order_by('-introduced', 'number_only')[:25]

    @override
    def item_title(self, item: Bill) -> str:
        return "Bill %s (%s)" % (item.number, "Private member's" if item.privatemember else "Government")

    @override
    def item_description(self, item: Bill) -> str:
        return item.name

    @override
    def item_link(self, item: Bill) -> str:
        return item.get_absolute_url()


class BillFeed(Feed):

    @override
    def get_object(self, request: HttpRequest, bill_id: str) -> Bill:
        return get_object_or_404(Bill, pk=bill_id)

    @override
    def title(self, bill: Bill) -> str:
        return "Bill %s" % bill.number

    @override
    def link(self, bill: Bill) -> str:
        return "http://openparliament.ca" + bill.get_absolute_url()

    @override
    def description(self, bill: Bill) -> str:
        return "From openparliament.ca, speeches about Bill %s, %s" % (bill.number, bill.name)

    @override
    def items(self, bill: Bill) -> List[Statement | VoteQuestion]:
        statements = (bill.statement_set.all()
                      .order_by('-time', '-sequence')
                      .select_related('member', 'member__politician', 'member__riding', 'member__party')[:10])
        votes = bill.votequestion_set.all().order_by('-date', '-number')[:3]
        merged = list(votes) + list(statements)
        merged.sort(key=lambda i: i.date, reverse=True)
        return merged

    @override
    def item_title(self, item: Statement | VoteQuestion) -> str:
        if isinstance(item, VoteQuestion):
            return "Vote #%s (%s)" % (item.number, item.get_result_display())

        return "%(name)s (%(party)s%(date)s)" % {
            'name': item.name_info['display_name'],
            'party': item.member.party.short_name + '; ' if item.member else '',
            'date': format_date(item.time, "F jS"),
        }

    @override
    def item_link(self, item: Statement | VoteQuestion) -> str:
        return item.get_absolute_url()

    @override
    def item_description(self, item: Statement | VoteQuestion) -> str:
        if isinstance(item, Statement):
            return item.text_html()

        return item.description

    @override
    def item_pubdate(self, item: Statement | VoteQuestion) -> datetime.datetime:
        return datetime.datetime(item.date.year, item.date.month, item.date.day)
