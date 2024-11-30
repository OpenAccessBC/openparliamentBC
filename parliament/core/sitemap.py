from typing import override

from django.contrib.sitemaps import Sitemap

from parliament.bills.models import Bill, VoteQuestion
from parliament.core.models import Politician
from parliament.hansards.models import Document


class PoliticianSitemap(Sitemap):

    @override
    def items(self):
        return Politician.objects.elected()


class HansardSitemap(Sitemap):

    @override
    def items(self):
        return Document.objects.all()

    def lastmod(self, obj):
        return obj.date


class BillSitemap(Sitemap):

    @override
    def items(self):
        return Bill.objects.all()


class VoteQuestionSitemap(Sitemap):
    @override
    def items(self):
        return VoteQuestion.objects.all()

    def lastmod(self, obj):
        return obj.date


sitemaps = {
    'politician': PoliticianSitemap,
    'hansard': HansardSitemap,
    'bill': BillSitemap,
    'votequestion': VoteQuestionSitemap,
}
