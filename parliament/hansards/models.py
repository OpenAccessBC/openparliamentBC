# coding: utf-8

import datetime
import logging
import os
import re
from collections import OrderedDict, defaultdict
from typing import Any, cast, override

from django.conf import settings
from django.db import models
from django.db.models import QuerySet
from django.template.defaultfilters import slugify
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from parliament.activity import utils as activity
from parliament.core import parsetools
from parliament.core.models import ElectedMember, Politician, Session
from parliament.core.utils import language_property, memoize_property
from parliament.search.index import register_search_model

logger = logging.getLogger(__name__)


class DebateManager(models.Manager["Document"]):

    @override
    def get_queryset(self) -> QuerySet["Document"]:
        return super(DebateManager, self).get_queryset().filter(document_type=Document.DEBATE)


class EvidenceManager(models.Manager["Document"]):

    @override
    def get_queryset(self) -> QuerySet["Document"]:
        return super(EvidenceManager, self).get_queryset().filter(document_type=Document.EVIDENCE)


class NoStatementManager(models.Manager["Document"]):
    """Manager restricts to Documents that haven't had statements parsed."""

    @override
    def get_queryset(self) -> QuerySet["Document"]:
        return super(NoStatementManager, self).get_queryset()\
            .annotate(scount=models.Count('statement'))\
            .exclude(scount__gt=0)


class Document(models.Model):

    DEBATE = 'D'
    EVIDENCE = 'E'

    document_type = models.CharField(max_length=1, db_index=True, choices=(
        ('D', 'Debate'),
        ('E', 'Committee Evidence'),
    ))
    date = models.DateField(blank=True, null=True)
    number = models.CharField(max_length=6, blank=True)  # there exist 'numbers' with letters
    session = models.ForeignKey(Session, on_delete=models.CASCADE)

    source_id = models.IntegerField(unique=True, db_index=True)

    most_frequent_word = models.CharField(max_length=20, blank=True)
    wordcloud = models.ImageField(upload_to='autoimg/wordcloud', blank=True, null=True)

    downloaded = models.BooleanField(
        default=False,
        help_text="Has the source data been downloaded?")
    skip_parsing = models.BooleanField(
        default=False,
        help_text="Don't try to parse this, presumably because of errors in the source.")

    public = models.BooleanField("Display on site?", default=False)
    multilingual = models.BooleanField("Content parsed in both languages?", default=False)

    objects = models.Manager()
    debates = DebateManager()
    evidence = EvidenceManager()
    without_statements = NoStatementManager()

    class Meta:
        ordering = ('-date',)

    @override
    def __str__(self) -> str:
        if self.document_type == self.DEBATE:
            return "Hansard #%s for %s (#%s/#%s)" % (self.number, self.date, self.id, self.source_id)

        return "%s evidence for %s (#%s/#%s)" % (
            self.committeemeeting.committee.short_name, self.date, self.id, self.source_id)

    @memoize_property
    def get_absolute_url(self) -> str | None:
        match self.document_type:
            case self.DEBATE:
                return reverse('debate', kwargs={
                    'year': self.date.year, 'month': self.date.month, 'day': self.date.day
                })
            case self.EVIDENCE:
                return self.committeemeeting.get_absolute_url()
            case _:
                return None

    def get_text_analysis_url(self):
        # Let's violate DRY!
        base_url = self.get_absolute_url()
        if base_url is None:
            raise TypeError("text analysis base url was unspecified")

        return base_url + 'text-analysis/'

    def to_api_dict(self, representation: str) -> dict[str, Any]:
        d = {
            "date": str(self.date) if self.date else None,
            "number": self.number,
            "most_frequent_word": {'en': self.most_frequent_word},
        }
        if representation == 'detail':
            d.update(
                source_id=self.source_id,
                source_url=self.source_url,
                session=self.session_id,
                document_type=self.get_document_type_display(),
            )
        return d

    @property
    def url(self) -> str | None:
        return self.source_url

    @property
    @memoize_property
    def source_url(self) -> str | None:
        match self.document_type:
            case self.DEBATE:
                return "https://www.ourcommons.ca/DocumentViewer/%(lang)s/%(sessid)s/house/sitting-%(sitting)s/hansard" % {
                    'lang': 'en',
                    'sessid': self.session_id,
                    'sitting': self.number
                }
            case self.EVIDENCE:
                return self.committeemeeting.evidence_url
            case _:
                return None

    def _topics(self, lst):
        topics = []
        last_topic = ''
        for statement in lst:
            if statement[0] and statement[0] != last_topic:
                last_topic = statement[0]
                topics.append((statement[0], statement[1]))
        return topics

    def topics(self):
        """Returns a tuple with (topic, statement slug) for every topic mentioned."""
        return self._topics(self.statement_set.all().values_list('h2_' + settings.LANGUAGE_CODE, 'slug'))

    def headings(self):
        """Returns a tuple with (heading, statement slug) for every heading mentioned."""
        return self._topics(self.statement_set.all().values_list('h1_' + settings.LANGUAGE_CODE, 'slug'))

    def topics_with_qp(self):
        """Returns the same as topics(), but with a link to Question Period at the start of the list."""
        statements = self.statement_set.all().values_list(
            'h2_' + settings.LANGUAGE_CODE, 'slug', 'h1_' + settings.LANGUAGE_CODE)
        topics = self._topics(statements)
        qp_seq = None
        for s in statements:
            if s[2] == 'Oral Questions':
                qp_seq = s[1]
                break
        if qp_seq is not None:
            topics.insert(0, ('Question Period', qp_seq))
        return topics

    @memoize_property
    def speaker_summary(self):
        """Returns a sorted dictionary (in order of appearance) summarizing the people
        speaking in this document.

        Keys are names, suitable for displays. Values are dicts with keys:
            slug: Slug of first statement by the person
            politician: Boolean -- is this an MP?
            description: Short title or affiliation
        """
        ids_seen = set()
        speakers = OrderedDict()
        for st in self.statement_set.filter(who_hocid__isnull=False).values_list(
                'who_' + settings.LANGUAGE_CODE,            # 0
                'who_context_' + settings.LANGUAGE_CODE,    # 1
                'slug',                                     # 2
                'politician__name',                         # 3
                'who_hocid'):                               # 4
            if st[4] in ids_seen:
                continue
            ids_seen.add(st[4])
            if st[3]:
                who = st[3]
            else:
                who = parsetools.r_parens.sub('', st[0])
                who = re.sub(r'^\s*\S+\s+', '', who).strip()  # strip honorific
            if who not in speakers:
                info = {
                    'slug': st[2],
                    'politician': bool(st[3])
                }
                if st[1]:
                    info['description'] = st[1]
                speakers[who] = info
        return speakers

    def outside_speaker_summary(self):
        """Same as speaker_summary, but only non-MPs."""
        return OrderedDict(
            [(k, v) for k, v in list(self.speaker_summary().items()) if not v['politician']]
        )

    def mp_speaker_summary(self):
        """Same as speaker_summary, but only MPs."""
        return OrderedDict(
            [(k, v) for k, v in list(self.speaker_summary().items()) if v['politician']]
        )

    def save_activity(self) -> None:
        statements = self.statement_set.filter(procedural=False).select_related('member', 'politician')
        politicians = {s.politician for s in statements if s.politician}
        for pol in politicians:
            topics: dict[str, list[str]] = {}
            wordcount = 0
            for statement in [s for s in statements if s.politician == pol]:
                wordcount += statement.wordcount
                if statement.topic in topics:
                    # If our statement is longer than the previous statement on this topic,
                    # use its text for the excerpt.
                    if len(statement.text_plain()) > len(topics[statement.topic][1]):
                        topics[statement.topic][1] = statement.text_plain()
                        topics[statement.topic][2] = statement.get_absolute_url()
                else:
                    topics[statement.topic] = [statement.slug, statement.text_plain(), statement.get_absolute_url()]
            for topic, topic_info in topics.items():
                if self.document_type == Document.DEBATE:
                    activity.save_activity({
                        'topic': topic,
                        'url': topic_info[2],
                        'text': topic_info[1],
                    }, politician=pol, date=self.date, guid='statement_%s' % topic_info[2], variety='statement')
                elif self.document_type == Document.EVIDENCE:
                    assert len(topics) == 1
                    if wordcount < 80:
                        continue
                    (_, text, url) = list(topics.values())[0]
                    activity.save_activity({
                        'meeting': self.committeemeeting,
                        'committee': self.committeemeeting.committee,
                        'text': text,
                        'url': url,
                        'wordcount': wordcount,
                    }, politician=pol, date=self.date, guid='cmte_%s' % url, variety='committee')

    def get_filename(self, language: str) -> str:
        assert self.source_id
        assert language in ('en', 'fr')
        return '%d-%s.xml' % (self.source_id, language)

    def get_filepath(self, language: str) -> str:
        filename = self.get_filename(language)
        if hasattr(settings, 'HANSARD_CACHE_DIR'):
            return os.path.join(settings.HANSARD_CACHE_DIR, filename)

        return os.path.join(settings.MEDIA_ROOT, 'document_cache', filename)

    def _save_file(self, path: str, content: bytes) -> None:
        with open(path, 'wb') as out:
            out.write(content)

    def get_cached_xml(self, language: str):
        if not self.downloaded:
            raise Exception("Not yet downloaded")
        return open(self.get_filepath(language), encoding='utf8')

    def delete_downloaded(self) -> None:
        for lang in ('en', 'fr'):
            path = self.get_filepath(lang)
            if os.path.exists(path):
                os.unlink(path)
        self.downloaded = False
        self.save()

    def save_xml(self, xml_en: bytes, xml_fr: bytes, overwrite: bool = False) -> None:
        if not overwrite and any(
                os.path.exists(p) for p in [self.get_filepath(lang) for lang in ['en', 'fr']]):
            raise Exception("XML files already exist")
        self._save_file(self.get_filepath('en'), xml_en)
        self._save_file(self.get_filepath('fr'), xml_fr)
        self.downloaded = True
        self.save()


@register_search_model
class Statement(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    time = models.DateTimeField(db_index=True)
    source_id = models.CharField(max_length=15, blank=True)

    slug = models.SlugField(max_length=100, blank=True)
    urlcache = models.CharField(max_length=200, blank=True)

    h1_en = models.CharField(max_length=300, blank=True)
    h2_en = models.CharField(max_length=300, blank=True)
    h3_en = models.CharField(max_length=300, blank=True)
    h1_fr = models.CharField(max_length=400, blank=True)
    h2_fr = models.CharField(max_length=400, blank=True)
    h3_fr = models.CharField(max_length=400, blank=True)

    member = models.ForeignKey(ElectedMember, blank=True, null=True, on_delete=models.CASCADE)
    # a shortcut -- should == member.politician
    politician = models.ForeignKey(Politician, blank=True, null=True, on_delete=models.CASCADE)
    who_en = models.CharField(max_length=300, blank=True)
    who_fr = models.CharField(max_length=500, blank=True)
    who_hocid = models.PositiveIntegerField(blank=True, null=True, db_index=True)
    who_context_en = models.CharField(max_length=300, blank=True)
    who_context_fr = models.CharField(max_length=500, blank=True)

    content_en = models.TextField()
    content_fr = models.TextField(blank=True)
    sequence = models.IntegerField(db_index=True)
    wordcount = models.IntegerField()
    wordcount_en = models.PositiveSmallIntegerField(
        null=True, help_text="# words originally spoken in English")

    procedural = models.BooleanField(default=False, db_index=True)
    written_question = models.CharField(max_length=1, blank=True, choices=(
        ('Q', 'Question'),
        ('R', 'Response')
    ))
    statement_type = models.CharField(max_length=35, blank=True)

    bills = models.ManyToManyField('bills.Bill', blank=True)
    mentioned_politicians = models.ManyToManyField(Politician, blank=True, related_name='statements_with_mentions')

    class Meta:
        ordering = ('sequence',)
        unique_together = (
            ('document', 'slug')
        )

    h1 = language_property('h1')
    h2 = language_property('h2')
    h3 = language_property('h3')
    who = language_property('who')
    who_context = language_property('who_context')

    @override
    def save(self, *args: Any, **kwargs: Any) -> None:
        self.content_en = self.content_en.replace('\n', '').replace('</p>', '</p>\n').strip()
        self.content_fr = self.content_fr.replace('\n', '').replace('</p>', '</p>\n').strip()
        if self.wordcount_en is None:
            self._generate_wordcounts()
        if ((not self.procedural) and self.wordcount <= 300
            and (
                (parsetools.r_notamember.search(self.who) and re.search(r'(Speaker|Chair|président)', self.who))
                or (not self.who)
                or not any(p for p in self.content_en.split('\n') if 'class="procedural"' not in p)
        )):
            # Some form of routine, procedural statement (e.g. somethng short by the speaker)
            self.procedural = True
        if not self.urlcache:
            self.generate_url()
        super(Statement, self).save(*args, **kwargs)

    @property
    def date(self) -> datetime.date:
        return datetime.date(self.time.year, self.time.month, self.time.day)

    def generate_url(self) -> None:
        self.urlcache = "%s%s/" % (
            self.document.get_absolute_url(),
            (self.slug if self.slug else self.sequence))

    def get_absolute_url(self) -> str:
        if not self.urlcache:
            self.generate_url()
        return self.urlcache

    @override
    def __str__(self) -> str:
        return "%s speaking about %s around %s" % (self.who, self.topic, self.time)

    def content_floor(self) -> str:
        if not self.content_fr:
            return self.content_en
        el, fl = self.content_en.split('\n'), self.content_fr.split('\n')
        if len(el) != len(fl):
            logger.error("Different en/fr paragraphs in %s", self.get_absolute_url())
            return self.content_en
        r = []
        for e, f in zip(el, fl):
            idx = e.find('data-originallang="')
            if idx and e[idx + 19:idx + 21] == 'fr':
                r.append(f)
            else:
                r.append(e)
        return "\n".join(r)

    def content_floor_if_necessary(self) -> str:
        """Returns text spoken in the original language(s), but only if that would
        be different than the content in the default language."""
        if not (self.content_en and self.content_fr):
            return ''

        lang_matches = re.finditer(r'data-originallang="(\w\w)"', getattr(self, 'content_' + settings.LANGUAGE_CODE))
        if any(m.group(1) != settings.LANGUAGE_CODE for m in lang_matches):
            return self.content_floor()

        return ''

    def text_html(self, language: str = settings.LANGUAGE_CODE) -> str:
        return mark_safe(getattr(self, 'content_' + language))

    def text_plain(self, language: str = settings.LANGUAGE_CODE) -> str:
        return self.html_to_text(getattr(self, 'content_' + language))

    @staticmethod
    def html_to_text(text: str) -> str:
        return strip_tags(
            text
            .replace('\n', '')
            .replace('<br>', '\n')
            .replace('</p>', '\n\n')
            .replace('&amp;', '&')
        ).strip()

    def search_dict(self):
        name = self.name_info
        d = {
            "text": self.text_plain(),
            # the date is local Ottawa time, not UTC, but we'll pretend for search
            "date": self.time.isoformat() + 'Z',
            "who_hocid": self.who_hocid,
            "topic": self.h2,
            "url": self.get_absolute_url(),
            "doc_url": self.document.get_absolute_url(),
            "committee": self.committee_name,
            "committee_slug": self.committee_slug
        }
        if self.member:
            d['party'] = self.member.party.short_name
            d['province'] = self.member.riding.province
            d['politician_id'] = self.member.politician.identifier

        d['doctype'] = 'committee' if d['committee'] else 'debate'
        d['politician'] = name['display_name']
        d['searchtext'] = f"{name['display_name']} {name['post'] if name['post'] else ''} {d.get('party', '')} {d['topic']} {d['text']}"
        return d

    def search_should_index(self) -> bool:
        return True

    @classmethod
    def search_get_qs(cls) -> QuerySet["Statement"]:
        qs = cls.objects.all().prefetch_related(
            'member__politician', 'member__party', 'member__riding', 'document',
            'document__committeemeeting__committee'
        ).order_by()
        if settings.LANGUAGE_CODE.startswith('fr'):
            qs = qs.exclude(content_fr='')
        return qs

    def _generate_wordcounts(self) -> None:
        paragraphs: list[list[str]] = [
            [],  # english
            [],  # french
            []  # procedural
        ]

        for para in self.content_en.split('\n'):
            idx = para.find('data-originallang="')
            if idx == -1:
                paragraphs[2].append(para)
            else:
                lang = para[idx + 19:idx + 21]
                if lang == 'en':
                    paragraphs[0].append(para)
                elif lang == 'fr':
                    paragraphs[1].append(para)
                else:
                    paragraphs[0].append(para)
                    logger.warning("Unrecognized language %s", lang)

        counts = [
            len(self.html_to_text(' '.join(p)).split())
            for p in paragraphs
        ]

        self.wordcount = counts[0] + counts[1]
        self.wordcount_en = counts[0]
        # self.wordcount_procedural = counts[2]

    # temp compatibility
    @property
    def heading(self) -> str:
        return self.h1

    @property
    def topic(self) -> str:
        return self.h2

    def to_api_dict(self, representation: str) -> dict[str, Any]:
        d: dict[str, str | dict[str, str] | bool | None] = {
            "time": str(self.time) if self.time else None,
            "attribution": {'en': self.who_en, 'fr': self.who_fr},
            "content": {'en': self.content_en, 'fr': self.content_fr},
            "url": self.get_absolute_url(),
            "politician_url": self.politician.get_absolute_url() if self.politician else None,
            "politician_membership_url": reverse(
                'politician_membership',
                kwargs={'member_id': self.member_id}) if self.member_id else None,
            "procedural": self.procedural,
            "source_id": self.source_id
        }
        for h in ('h1', 'h2', 'h3'):
            if getattr(self, h):
                d[h] = {'en': getattr(self, h + '_en'), 'fr': getattr(self, h + '_fr')}

        if d['url']:
            d['document_url'] = cast(str, d['url'])[:d['url'].rstrip('/').rfind('/') + 1]
        return d

    @property
    @memoize_property
    def name_info(self) -> dict[str, Any]:
        info: dict[str, Any] = {
            'post': None,
            'named': True
        }
        if not self.member:
            info['display_name'] = parsetools.r_mister.sub('', self.who)
            if self.who_context:
                if self.who_context in self.who:
                    info['display_name'] = parsetools.r_parens.sub('', info['display_name'])
                    info['post'] = self.who_context
                else:
                    info['post_reminder'] = self.who_context
                if self.who_hocid:
                    info['url'] = '/search/?q=Witness%%3A+%%22%s%%22' % self.who_hocid
        else:
            info['url'] = self.member.politician.get_absolute_url()
            if parsetools.r_notamember.search(self.who):
                info['display_name'] = self.who
                if self.member.politician.name in self.who:
                    info['display_name'] = re.sub(r'\(.+\)', '', self.who)
                info['named'] = False
            elif '(' not in self.who or not parsetools.r_politicalpost.search(self.who):
                info['display_name'] = self.member.politician.name
            else:
                post_match = re.search(r'\((.+)\)', self.who)
                if post_match:
                    info['post'] = post_match.group(1).split(',')[0]
                info['display_name'] = self.member.politician.name
        return info

    @staticmethod
    def set_slugs(statements: list["Statement"]) -> None:
        counter: dict[str, int] = defaultdict(int)
        for statement in statements:
            slug = slugify(statement.name_info['display_name'])[:50]
            if not slug:
                slug = 'procedural'
            counter[slug] += 1
            statement.slug = slug + '-%s' % counter[slug]

    @property
    def committee_name(self) -> str:
        if self.document.document_type != Document.EVIDENCE:
            return ''
        return self.document.committeemeeting.committee.short_name

    @property
    def committee_slug(self) -> str:
        if self.document.document_type != Document.EVIDENCE:
            return ''
        return self.document.committeemeeting.committee.slug


class OldSequenceMapping(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField()
    slug = models.SlugField(max_length=100)

    class Meta:
        unique_together = (
            ('document', 'sequence')
        )

    @override
    def __str__(self) -> str:
        return "%s -> %s" % (self.sequence, self.slug)
