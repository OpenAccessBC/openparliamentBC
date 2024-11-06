from django.urls import re_path

from parliament.committees.views import (CommitteeAnalysisView, CommitteeMeetingListView, committee, committee_activity,
                                         committee_id_redirect, committee_list, committee_meeting,
                                         committee_meeting_statement, committee_year_archive, evidence_analysis,
                                         evidence_permalink)

urlpatterns = [
    re_path(r'^$', committee_list, name='committee_list'),
    re_path(r'^activities/(?P<activity_id>\d+)/$', committee_activity, name='committee_activity'),
    re_path(r'^meetings/$', CommitteeMeetingListView.as_view(), name='committee_meetings'),
    re_path(r'^(?P<slug>[^/]+)/(?P<year>2\d\d\d)/$', committee_year_archive, name='committee_year_archive'),
    re_path(r'^(?P<committee_slug>[^/]+)/(?P<session_id>\d+-\d)/(?P<number>\d+)/$', committee_meeting, name='committee_meeting'),
    re_path(r'^(?P<committee_slug>[^/]+)/(?P<session_id>\d+-\d)/(?P<number>\d+)/text-analysis/$', evidence_analysis),
    re_path(r'^(?P<committee_slug>[^/]+)/(?P<session_id>\d+-\d)/(?P<number>\d+)/(?P<slug>[a-zA-Z0-9-]+)/$', committee_meeting_statement, name='committee_meeting'),
    re_path(r'^(?P<committee_slug>[^/]+)/(?P<session_id>\d+-\d)/(?P<number>\d+)/(?P<slug>[a-zA-Z0-9-]+)/only/$', evidence_permalink, name='evidence_permalink'),
    re_path(r'^(?P<committee_id>\d+)/', committee_id_redirect),
    re_path(r'^(?P<slug>[^/]+)/$', committee, name='committee'),
    re_path(r'^(?P<committee_slug>[^/]+)/analysis/$', CommitteeAnalysisView.as_view(), name='committee_analysis'),
]
