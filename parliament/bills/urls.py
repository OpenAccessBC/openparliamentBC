from django.http import HttpResponsePermanentRedirect
from django.urls import re_path, reverse

from parliament.bills.views import BillFeed, BillListFeed, bill, bill_pk_redirect, bills_for_session, index

urlpatterns = [
    re_path(r'^(?P<session_id>\d+-\d)/(?P<bill_number>[CS]-[0-9A-Z]+)/$', bill, name='bill'),
    re_path(r'^(?P<bill_id>\d+)/rss/$', BillFeed(), name='bill_feed'),
    re_path(r'^(?:session/)?(?P<session_id>\d+-\d)/$', bills_for_session, name='bills_for_session'),
    re_path(r'^$', index, name='bills'),
    re_path(r'^(?P<bill_id>\d+)/$', bill_pk_redirect),
    re_path(r'^rss/$', BillListFeed(), name='bill_list_feed'),
    re_path(r'^votes/([0-9/-]*)$', lambda r, u: HttpResponsePermanentRedirect(
        reverse('votes') + u)),
]
