import datetime
from typing import Any, override

from django.conf import settings
from django.contrib.syndication.views import Feed
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.template import loader
from django.utils.html import conditional_escape
from django.views.decorators.cache import never_cache

from parliament.bills.models import VoteQuestion
from parliament.core.models import Session, SiteNews
from parliament.core.templatetags.markup import markdown
from parliament.hansards.models import Document
from parliament.text_analysis.models import TextAnalysis


def home(request: HttpRequest) -> HttpResponse:
    t = loader.get_template("home.html")
    latest_hansard = Document.debates.filter(date__isnull=False, public=True)[0]
    c = {
        'latest_hansard': latest_hansard,
        'sitenews': SiteNews.objects.filter(
            active=True,
            date__gte=datetime.datetime.now() - datetime.timedelta(days=90))[:6],
        'votes': VoteQuestion.objects.filter(session=Session.objects.current()).select_related('bill')[:6],
        'wordcloud_js': TextAnalysis.objects.get_wordcloud_js(key=latest_hansard.get_text_analysis_url())
    }
    return HttpResponse(t.render(c, request))


@never_cache
def closed(request: HttpRequest, message: str | None = None) -> HttpResponse:
    if not message:
        message = "We're currently down for planned maintenance. We'll be back soon."
    resp = flatpage_response(request, 'closedparliament.ca', message)
    resp.status_code = 503
    return resp


@never_cache
def db_readonly(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
    title = "Temporarily unavailable"
    message = """We're currently running on our backup database, and this particular functionality is down.
        It should be back up soon. Sorry for the inconvenience!"""
    resp = flatpage_response(request, title, message)
    resp.status_code = 503
    return resp


def disable_on_readonly_db(view):
    if settings.PARLIAMENT_DB_READONLY:
        return db_readonly
    return view


def flatpage_response(request: HttpRequest, title: str, message: str) -> HttpResponse:
    t = loader.get_template("flatpages/default.html")
    c = {
        'flatpage': {
            'title': title,
            'content': ("""<div class="row align-right"><div class="main-col"><p>%s</p></div></div>"""
                        % conditional_escape(message))
        },
    }
    return HttpResponse(t.render(c, request))


class SiteNewsFeed(Feed[SiteNews, SiteNews]):

    title = "openparliament.ca: Site news"
    link = "http://openparliament.ca/"
    description = "Announcements about the openparliament.ca site"

    @override
    def items(self) -> QuerySet[SiteNews]:
        return SiteNews.public.all()[:6]

    @override
    def item_title(self, item: SiteNews) -> str:
        return item.title

    @override
    def item_description(self, item: SiteNews) -> str:
        return markdown(item.text)

    @override
    def item_link(self, item: SiteNews) -> str:
        return 'http://openparliament.ca/'

    @override
    def item_guid(self, item: SiteNews) -> str:
        return str(item.id)
