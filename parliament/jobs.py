import time

from django.db import transaction, models

from parliament.politicians import twit
from parliament.politicians import googlenews as gnews
from parliament.imports import parlvotes, legisinfo, hans
from parliament.core.models import Politician, Session
from parliament.core import datautil
from parliament.hansards.models import Hansard
from parliament.activity import utils as activityutils
from parliament.activity.models import Activity

@transaction.commit_on_success
def twitter():
    twit.save_tweets()
    return True
    
def googlenews():
    for pol in Politician.objects.current():
        gnews.save_politician_news(pol)
        time.sleep(1)
        
def votes():
    parlvotes.import_votes()
    
@transaction.commit_on_success
def bills():
    legisinfo.import_bills(Session.objects.current())
    return True

@transaction.commit_on_success
def prune_activities():
    for pol in Politician.objects.current():
        activityutils.prune(Activity.objects.filter(politician=pol))
    return True
    
@transaction.commit_on_success
def hansards():
    datautil.hansards_from_calendar()
    for hansard in Hansard.objects.all().annotate(scount=models.Count('statement')).exclude(scount__gt=0).order_by('date').iterator():
        hans.parseAndSave(hansard)
        hansard.save_activity()
    return True