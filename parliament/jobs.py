import datetime
import logging

from django.db import models, transaction

from parliament.activity import utils as activityutils
from parliament.activity.models import Activity
from parliament.core.models import Politician, Session
from parliament.hansards.models import Document
from parliament.imports import legisinfo, parl_cmte, parl_document, parlvotes
from parliament.imports.mps import update_mps_from_ourcommons
from parliament.text_analysis import corpora

logger = logging.getLogger(__name__)

mps = update_mps_from_ourcommons


def votes():
    parlvotes.import_votes()


def bills():
    legisinfo.import_bills(Session.objects.current())


@transaction.atomic
def prune_activities():
    for pol in Politician.objects.current():
        activityutils.prune(Activity.public.filter(politician=pol))
    return True


def committee_evidence():
    evidences = (Document.evidence
                 .annotate(scount=models.Count('statement'))
                 .exclude(scount__gt=0)
                 .exclude(skip_parsing=True)
                 .order_by('date'))
    for document in evidences.iterator():
        try:
            print(document)
            parl_document.import_document(document, interactive=False)
            if document.statement_set.all().count():
                document.save_activity()
        except Exception as e:
            logger.exception("Evidence parse failure on #%s: %r", document.id, e)
            continue


def committees(sess=None):
    if sess is None:
        sess = Session.objects.current()
        if sess.start >= datetime.date.today():
            return
    try:
        parl_cmte.import_committee_list(session=sess)
    except Exception:
        logger.exception("Committee list import failure")
    parl_cmte.import_committee_documents(sess)


def committees_full():
    committees()
    committee_evidence()


@transaction.atomic
def hansards_load():
    parl_document.fetch_latest_debates()


def hansards_parse():
    debates = (Document.objects
               .filter(document_type=Document.DEBATE)
               .annotate(scount=models.Count('statement'))
               .exclude(scount__gt=0)
               .exclude(skip_parsing=True)
               .order_by('date'))
    for hansard in debates.iterator():
        with transaction.atomic():
            try:
                with transaction.atomic():
                    parl_document.import_document(hansard, interactive=False)
            except Exception as e:
                logger.exception("Hansard parse failure on #%s: %r", hansard.id, e)
                continue
            # now reload the Hansard to get the date
            hansard = Document.objects.get(pk=hansard.id)
            hansard.save_activity()


def hansards():
    hansards_load()
    hansards_parse()


def corpus_for_debates():
    corpora.generate_for_debates()


def corpus_for_committees():
    corpora.generate_for_committees()
