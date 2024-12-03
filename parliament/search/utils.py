import math
import re
from collections import namedtuple
from re import Match
from typing import Dict

_FakePaginator = namedtuple('_FakePaginator', 'num_pages count')


class SearchPaginator():
    """A dumb imitation of the Django Paginator."""

    def __init__(self, object_list, hits, pagenum, perpage):
        self.object_list = object_list
        self.hits = hits
        self.num_pages = int(math.ceil(float(self.hits) / float(perpage)))
        self.number = pagenum
        self.start_index = ((pagenum - 1) * perpage) + 1
        self.end_index = self.start_index + perpage - 1
        self.end_index = min(self.end_index, self.hits)

    @property
    def paginator(self):
        return _FakePaginator(self.num_pages, self.hits)

    def has_previous(self):
        return self.number > 1

    def has_next(self):
        return self.number < self.num_pages

    def previous_page_number(self):
        return self.number - 1

    def next_page_number(self):
        return self.number + 1


class BaseSearchQuery():

    ALLOWABLE_FILTERS: Dict[str, str] = {}

    def __init__(self, query):
        self.raw_query = query
        self.filters: Dict[str, str] = {}

        def extract_filter(match: Match) -> str:
            self.filters[match.group(1)] = match.group(2)
            return ''

        self.bare_query = re.sub(r'(%s): "([^"]+)"' % '|'.join(self.ALLOWABLE_FILTERS), extract_filter, self.raw_query)
        self.bare_query = re.sub(r'\s\s+', ' ', self.bare_query).strip()

    @property
    def normalized_query(self):
        query_sep = ' ' if self.bare_query and self.filters else ''
        query_filter = ' '.join(('%s: "%s"' % (key, self.filters[key]) for key in sorted(self.filters.keys())))
        q = self.bare_query + query_sep + query_filter
        return q.strip()
