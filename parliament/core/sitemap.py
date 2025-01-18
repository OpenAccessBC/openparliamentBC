import datetime
from typing import override

from django.contrib.sitemaps import Sitemap
from django.db.models import QuerySet

from parliament.bills.models import Bill, VoteQuestion
from parliament.core.models import Politician
from parliament.hansards.models import Document


class PoliticianSitemap(Sitemap[Politician]):

    @override
    def items(self) -> QuerySet[Politician]:
        return Politician.objects.elected()


class HansardSitemap(Sitemap[Document]):

    @override
    def items(self) -> QuerySet[Document]:
        return Document.objects.all()

    def lastmod(self, obj: Document) -> datetime.date:
        return obj.date


class BillSitemap(Sitemap[Bill]):

    @override
    def items(self) -> QuerySet[Bill]:
        return Bill.objects.all()


class VoteQuestionSitemap(Sitemap[VoteQuestion]):
    @override
    def items(self) -> QuerySet[VoteQuestion]:
        return VoteQuestion.objects.all()

    def lastmod(self, obj: VoteQuestion) -> datetime.date:
        return obj.date


sitemaps = {
    'politician': PoliticianSitemap,
    'hansard': HansardSitemap,
    'bill': BillSitemap,
    'votequestion': VoteQuestionSitemap,
}
