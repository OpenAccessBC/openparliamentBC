"""Parse XML transcripts from ourcommons.ca.

These transcripts are either House Hansards, or House committee evidence.

Most of the heavily-lifting code has been put in a separate module
called alpheus.
"""
import logging
import re
import sys
from difflib import SequenceMatcher
from re import Match
from typing import Any, cast
from xml.sax.saxutils import quoteattr

import requests
from django.db import transaction
from django.urls import reverse
from lxml import etree

from parliament.bills.models import Bill, BillInSession, VoteQuestion
from parliament.core.models import ElectedMember, Politician, Session
from parliament.hansards.models import Document, OldSequenceMapping, Statement

from .alpheus import parse_string as alpheus_parse_string

logger = logging.getLogger(__name__)


@transaction.atomic
def import_document(document: Document, interactive: bool = True, reimport_preserving_sequence: bool = False) -> Document | None:
    old_statements = None
    if document.statement_set.all().exists():
        if reimport_preserving_sequence:
            if OldSequenceMapping.objects.filter(document=document).exists():
                logger.error("Sequence mapping already exits for %s", document)
                return None
            old_statements = list(document.statement_set.all())
            document.statement_set.all().delete()
        else:
            if not interactive:
                return None
            sys.stderr.write("Statements already exist for %r.\nDelete them? (y/n) " % document)
            if input().strip() != 'y':
                return None
            document.statement_set.all().delete()

    if not document.downloaded:
        return None
    xml_en = document.get_cached_xml('en')
    pdoc_en = alpheus_parse_string(xml_en.read())
    xml_en.close()

    xml_fr = document.get_cached_xml('fr')
    pdoc_fr = alpheus_parse_string(xml_fr.read())
    xml_fr.close()

    if document.date and document.date != pdoc_en.meta['date']:
        # Sometimes they get the date wrong
        if document.date != pdoc_fr.meta['date']:
            logger.error("Date mismatch on document #%s: %s %s",
                         document.id, document.date, pdoc_en.meta['date'])
    else:
        document.date = pdoc_en.meta['date']
    document.number = pdoc_en.meta['document_number']
    document.public = True

    statements: list[Statement] = []

    assert pdoc_en.statements is not None
    for pstate in pdoc_en.statements:
        s = Statement(
            document=document,
            sequence=len(statements),
            content_en=pstate.content,
            time=pstate.meta['timestamp'])
        s.source_id = pstate.meta['id']
        s.h1_en = pstate.meta.get('h1', '')
        s.h2_en = pstate.meta.get('h2', '')
        s.h3_en = pstate.meta.get('h3', '')

        if s.h1_en and not s.h2_en:
            s.h2_en = s.h3_en
            s.h3_en = ''

        s.who_en = pstate.meta.get('person_attribution', '')[:300]
        try:
            s.who_hocid = int(pstate.meta['person_id']) if pstate.meta.get('person_id') else None
        except ValueError:
            logger.warning("ValueError parsing person ID %s", pstate.meta['person_id'])
            s.who_hocid = None
        s.who_context_en = pstate.meta.get('person_context', '')[:300]

        s.statement_type = pstate.meta.get('intervention_type', '').lower()
        s.written_question = pstate.meta.get('written_question', '').upper()[:1]

        if s.who_hocid and not pstate.meta.get('person_type'):
            # At the moment. person_type is only set if we know the person
            # is a non-politician. This might change...
            try:
                s.politician = Politician.objects.get_by_parl_affil_id(s.who_hocid, session=cast(Session, document.session))
                s.member = ElectedMember.objects.get_by_pol(s.politician, date=document.date)
            except Politician.DoesNotExist:
                logger.info("Could not resolve speaking politician ID %s for %r", s.who_hocid, s.who)

        s._related_pols = set()
        s._related_bills = set()
        s.content_en = _process_related_links(s.content_en, s)

        statements.append(s)

    assert pdoc_fr.statements is not None
    if len(statements) != len(pdoc_fr.statements):
        logger.info("French and English statement counts don't match for %r", document)

    _r_paragraphs = re.compile(r'<p[^>]* data-HoCid=.+?</p>')
    _r_paragraph_id = re.compile(r'<p[^>]* data-HoCid="(?P<id>\d+)"')
    fr_paragraphs = {}
    fr_statements = {}
    missing_id_count = 0

    def _get_paragraph_id(p: str) -> int:
        return int(_r_paragraph_id.match(p).group('id'))

    def _get_paragraphs_and_ids(content: str) -> list[tuple[str, int]]:
        return [(p, _get_paragraph_id(p)) for p in _r_paragraphs.findall(content)]

    for alph_st in pdoc_fr.statements:
        if alph_st.meta['id']:
            fr_statements[alph_st.meta['id']] = alph_st
        for p, pid in _get_paragraphs_and_ids(alph_st.content):
            if pid:
                fr_paragraphs[pid] = p
            else:
                missing_id_count += 1

    def _substitute_french_content(match: Match[str]) -> str:
        try:
            pid = _get_paragraph_id(match.group(0))
            if pid:
                return fr_paragraphs[pid]

            return match.group(0)
        except KeyError:
            logger.error("Paragraph ID %s not found in French for %s", match.group(0), document)
            return match.group(0)

    if missing_id_count > float(len(fr_paragraphs)):
        logger.error("French paragraphs not available")
        document.multilingual = False
    else:
        document.multilingual = True
        for st in statements:
            fr_data = fr_statements.get(st.source_id)
            pids_en: list[int] = [pid for _, pid in _get_paragraphs_and_ids(st.content_en)]
            pids_fr: list[int] | None = [pid for _, pid in _get_paragraphs_and_ids(fr_data.content)] if fr_data else None
            if fr_data and pids_en == pids_fr:
                # Match by statement
                st.content_fr = _process_related_links(fr_data.content, st)
            elif all(pids_en):
                # Match by paragraph
                st.content_fr = _process_related_links(
                    _r_paragraphs.sub(_substitute_french_content, st.content_en),
                    st
                )
            else:
                logger.warning("Could not do multilingual match of statement %s", st.source_id)
                document.multilingual = False
            if fr_data:
                st.h1_fr = fr_data.meta.get('h1', '')
                st.h2_fr = fr_data.meta.get('h2', '')
                st.h3_fr = fr_data.meta.get('h3', '')
                if st.h1_fr and not st.h2_fr:
                    st.h2_fr = st.h3_fr
                    st.h3_fr = ''
                st.who_fr = fr_data.meta.get('person_attribution', '')[:300]
                st.who_context_fr = fr_data.meta.get('person_context', '')[:300]

    Statement.set_slugs(statements)

    if old_statements:
        for mapping in _align_sequences(statements, old_statements):
            OldSequenceMapping.objects.create(
                document=document,
                sequence=mapping[0],
                slug=mapping[1]
            )

    for s in statements:
        s.save()

        s.mentioned_politicians.add(*list(s._related_pols))
        s.bills.add(*list(s._related_bills))
        if getattr(s, '_related_vote', False):
            s._related_vote.context_statement = s
            s._related_vote.save()

    document.save()

    return document


def _align_sequences(new_statements: list[Statement], old_statements: list[Statement]) -> list[tuple[int, str]]:
    """Given two list of statements, returns a list of mappings in the form of
    (old_statement_sequence, new_statement_slug)"""

    def build_speaker_dict(states: list[Statement]) -> dict[str, list[Statement]]:
        d: dict[str, list[Statement]] = {}
        for s in states:
            d.setdefault(s.name_info['display_name'], []).append(s)
        return d

    def get_comparison_sequence(text: str) -> list[str]:
        return re.split(r'\s+', text)

    def calculate_similarity(old: Statement, new: Statement) -> float:
        """Given two statements, return a score between 0 and 1 expressing their similarity"""
        score = 0.8 if old.time == new.time else 0.0
        oldtext, newtext = old.text_plain(), new.text_plain()
        if new in chosen:
            score -= 0.01
        if newtext in oldtext:
            similarity = 1.0
        else:
            similarity = SequenceMatcher(
                None, get_comparison_sequence(oldtext), get_comparison_sequence(newtext)
            ).ratio()
        return (score + similarity) / 1.8

    new_speakers, old_speakers = build_speaker_dict(new_statements), build_speaker_dict(old_statements)
    mappings = []
    chosen = set()

    for speaker, olds in list(old_speakers.items()):
        news = new_speakers.get(speaker, [])
        if speaker and len(olds) == len(news):
            # The easy version: assume we've got the same statements
            for old, new in zip(olds, news):
                score = calculate_similarity(old, new)
                if score < 0.9:
                    logger.warning(
                        "Low similarity for easy match %s: %r %r / %r %r",
                        score, old, old.text_plain(), new, new.text_plain())
                mappings.append((old.sequence, new.slug))
        else:
            # Try and pair the most similar statement
            if news:
                logger.info("Count mismatch for %s", speaker)
                candidates = news
            else:
                logger.warning("No new statements for %s", speaker)
                candidates = new_statements  # Calculate similarity with all possibilities
            for old in olds:
                scores = ((cand, calculate_similarity(old, cand)) for cand in candidates)
                choice, score = max(scores, key=lambda s: s[1])
                chosen.add(choice)
                if score < 0.75:
                    logger.warning(
                        "Low-score similarity match %s: %r %r / %r %r",
                        score, old, old.text_plain(), choice, choice.text_plain())
                mappings.append((old.sequence, choice.slug))

    return mappings


def _process_related_links(content: str, statement: Statement) -> str:
    return re.sub(
        r'<a class="related_link (\w+)" ([^>]+)>(.*?)</a>',
        lambda m: _process_related_link(m, statement),
        content)


def _process_related_link(match: Match[str], statement: Statement) -> str:
    (link_type, tagattrs, text) = match.groups()
    params = {m.group(1): m.group(2) for m in re.finditer(r'data-([\w-]+)="([^"]+)"', tagattrs)}
    hocid = params['HoCid']
    if link_type == 'politician':
        try:
            pol = Politician.objects.get_by_parl_affil_id(hocid)
        except Politician.DoesNotExist:
            logger.warning("Could not resolve related politician #%s, %s", hocid, text)
            return text
        url = pol.get_absolute_url()
        title = pol.name
        statement._related_pols.add(pol)
    elif link_type == 'legislation':
        try:
            bis = BillInSession.objects.get_by_legisinfo_id(hocid)
            bill = cast(Bill, bis.bill)
            url = bis.get_absolute_url()
        except Bill.DoesNotExist:
            newmatch = re.search(r'\b[CS]\-\d+[A-E]?\b', text)
            if not newmatch:
                logger.error("Invalid bill link %s", text)
                return text

            match = newmatch
            bill = Bill.objects.create_temporary_bill(
                legisinfo_id=hocid,
                number=match.group(0), session=statement.document.session)
            url = bill.get_absolute_url()

        title = bill.name
        statement._related_bills.add(bill)
    elif link_type == 'vote':
        try:
            vote = VoteQuestion.objects.get(
                session=statement.document.session,
                number=int(params['number']))
            url = vote.get_absolute_url()
            title = vote.description
            statement._related_vote = vote
        except VoteQuestion.DoesNotExist:
            # We'll just operate on faith that the vote will soon
            # be created
            url = reverse('vote', kwargs={'session_id': statement.document.session_id, 'number': params['number']})
            title = None
    else:
        raise Exception("Unknown link type %s" % link_type)

    attrs = {
        'href': url,
        'data-HoCid': int(hocid)
    }
    if title:
        attrs['title'] = title
    return _build_tag('a', attrs) + text + '</a>'


def _build_tag(name: str, attrs: dict[str, Any]) -> str:
    return '<%s%s>' % (
        name,
        ''.join([" %s=%s" % (k, quoteattr(str(v))) for k, v in sorted(attrs.items())])
    )


def _test_has_paragraph_ids(elem: etree._Element) -> bool:
    """Do all, or almost all, of the paragraphs in this document have ID attributes?
    Sometimes they're missing at first."""
    paratext = elem.xpath('//ParaText')
    paratext_with_id = [pt for pt in paratext if pt.get('id')]
    return (len(paratext_with_id) / float(len(paratext))) > 0.95


HANSARD_URL = 'https://www.ourcommons.ca/Content/House/{parliamentnum}{sessnum}/Debates/{sitting:03d}/HAN{sitting:03d}-{lang}.XML'


class NoDocumentFound(Exception):
    pass


def fetch_latest_debates(session: Session | None = None) -> None:
    session_obj: Session = session or Session.objects.current()

    sittings = Document.objects.filter(document_type=Document.DEBATE, session=session_obj).values_list('number', flat=True)
    # FIXME at the moment ourcommons.ca doesn't make it easy to get a list of
    # debates; this is a quick temporary solution that will break on special
    # sittings like 128-B
    if len(sittings) == 0:
        max_sitting = 0
    else:
        max_sitting = max(int(n) for n in sittings if n.isdigit())

    while True:
        max_sitting += 1
        try:
            fetch_debate_for_sitting(session_obj, max_sitting)
        except NoDocumentFound:
            break


def fetch_debate_for_sitting(session: Session, sitting_number: int, import_without_paragraph_ids: bool = True) -> None:
    url = HANSARD_URL.format(
        parliamentnum=session.parliamentnum,
        sessnum=session.sessnum, sitting=sitting_number, lang='E')
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        if resp.status_code != 404:
            logger.error("Response %d from %s", resp.status_code, url)
        raise NoDocumentFound
    print(url)

    xml_en = resp.content
    url = HANSARD_URL.format(
        parliamentnum=session.parliamentnum,
        sessnum=session.sessnum, sitting=sitting_number, lang='F')
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    xml_fr = resp.content

    doc_en = etree.fromstring(xml_en)
    doc_fr = etree.fromstring(xml_fr)

    source_id = int(doc_en.get('id', -1))
    if Document.objects.filter(source_id=source_id).exists():
        raise Exception("Document at source_id %d already exists but not sitting %d" % (source_id, sitting_number))
    assert int(doc_fr.get('id', -1)) == source_id

    if ((not import_without_paragraph_ids)
            and not (_test_has_paragraph_ids(doc_en) and _test_has_paragraph_ids(doc_fr))):
        logger.warning("Missing paragraph IDs, cancelling")
        return

    with transaction.atomic():
        doc = Document.objects.create(
            document_type=Document.DEBATE,
            session=session,
            source_id=source_id,
            number=str(sitting_number)
        )
        doc.save_xml(xml_en, xml_fr)
        logger.info("Saved sitting %s", doc.number)


def refresh_xml(document: Document) -> None:
    """
    Download new XML from Parliament, reimport.
    """
    if document.document_type == Document.DEBATE:
        url_en = HANSARD_URL.format(
            parliamentnum=document.session.parliamentnum,
            sessnum=document.session.sessnum, sitting=int(document.number), lang='E')
        url_fr = HANSARD_URL.format(
            parliamentnum=document.session.parliamentnum,
            sessnum=document.session.sessnum, sitting=int(document.number), lang='F')
    else:
        raise NotImplementedError

    resp_en = requests.get(url_en, timeout=10)
    resp_en.raise_for_status()
    xml_en = resp_en.content

    resp_fr = requests.get(url_fr, timeout=10)
    resp_fr.raise_for_status()
    xml_fr = resp_fr.content

    document.save_xml(xml_en, xml_fr, overwrite=True)
    import_document(document)
