# coding: utf-8

import itertools
import re
from collections import defaultdict
from heapq import nlargest
from operator import itemgetter
from typing import Dict, FrozenSet, Generator, List, Tuple, override

STOPWORDS = frozenset(
    ["i", "me", "my", "myself", "we", "our", "ours", "ourselves",
     "you", "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
     "she", "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
     "theirs", "themselves", "what", "which", "who", "whom", "this", "that", "these",
     "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has",
     "had", "having", "do", "does", "did", "doing", "a", "an", "the", "and", "but", "if",
     "or", "because", "as", "until", "while", "of", "at", "by", "for", "with", "about",
     "against", "between", "into", "through", "during", "before", "after", "above",
     "below", "to", "from", "up", "down", "in", "out", "on", "off", "over", "under",
     "again", "further", "then", "once", "here", "there", "when", "where", "why", "how",
     "all", "any", "both", "each", "few", "more", "most", "other", "some", "such", "no",
     "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s", "t", "can",
     "will", "just", "don", "should", "now",  # this is the nltk stopwords list
     "it's", "we're", "we'll", "they're", "can't", "won't", "isn't", "don't", "he's",
     "she's", "i'm", "aren't", "government", "house", "committee", "would", "speaker",
     "motion", "mr", "mrs", "ms", "member", "minister", "canada", "members", "time",
     "prime", "one", "parliament", "us", "bill", "act", "like", "canadians", "people",
     "said", "want", "could", "issue", "today", "hon", "order", "party", "canadian",
     "think", "also", "new", "get", "many", "say", "look", "country", "legislation",
     "law", "department", "two", "day", "days", "madam", "must", "that's", "okay",
     "thank", "really", "much", "there's", "yes", "no"
     ]
)


r_punctuation = re.compile(r"[^\s\w0-9'’—-]", re.UNICODE)
r_whitespace = re.compile(r'[\s—]+')


def text_token_iterator(text: str) -> Generator[str]:
    text = r_punctuation.sub('', text.lower())
    yield from r_whitespace.split(text)


def statements_token_iterator(statements, statement_separator=None):
    for statement in statements:
        yield from text_token_iterator(statement.text_plain())
        if statement_separator is not None:
            yield statement_separator


def ngram_iterator(tokens, n=2):
    sub_iterators = itertools.tee(tokens, n)
    for i, iterator in enumerate(sub_iterators[1:]):
        # TODO: consume(iterator, i + 1)
        for _ in range(i + 1):
            # Advance the iterator i+1 times
            next(iterator, None)
    for words in zip(*sub_iterators):
        yield ' '.join(words)


class FrequencyModel(dict):
    """
    Given an iterable of strings, constructs an object mapping each string
    to the probability that a randomly chosen string will be it (that is,
    # of occurences of string / # total number of items).
    """

    def __init__(self, items: List[str], min_count: int = 1) -> None:
        counts: Dict[str, int] = defaultdict(int)
        total_count = 0
        for item in items:
            if len(item) > 2 and '/' not in item:
                counts[item] += 1
                total_count += 1
        self.count = total_count
        self.update(
            (k, v / float(total_count)) for k, v in counts.items() if v >= min_count
        )

    def __missing__(self, key: str) -> float:
        return float()

    def diff(self, other: "FrequencyModel") -> "FrequencyDiffResult":
        """
        Given another FrequencyModel, returns a FrequencyDiffResult containing the difference
        between the probability of a given word appears in this FrequencyModel vs the other
        background model.
        """
        r = FrequencyDiffResult()
        for k, _ in self.items():
            if k not in STOPWORDS:
                r[k] = self[k] - other[k]
        return r

    def item_count(self, key: str) -> int:
        return round(self[key] * self.count)

    def most_common(self, n: int | None = None) -> List[Tuple[str, int]]:
        if n is None:
            return sorted(iter(self.items()), key=itemgetter(1), reverse=True)
        return nlargest(n, iter(self.items()), key=itemgetter(1))

    @classmethod
    def from_statement_qs(cls, qs, ngram=1, min_count=1):
        it = statements_token_iterator(qs.iterator(), statement_separator='/')
        if ngram > 1:
            it = ngram_iterator(it, ngram)
        return cls(it, min_count=min_count)


class FrequencyDiffResult(dict):

    def __missing__(self, key: str) -> float:
        return float()

    def most_common(self, n: int = 10) -> List[Tuple[str, float]]:
        return nlargest(n, iter(self.items()), key=itemgetter(1))


class WordCounter(dict):

    def __init__(self, stopwords: FrozenSet[str] = STOPWORDS) -> None:
        self.stopwords: FrozenSet = stopwords
        super(WordCounter, self).__init__(self)

    def __missing__(self, key: str) -> int:
        return 0

    @override
    def __setitem__(self, key: str, value: int) -> None:
        if key not in self.stopwords:
            super(WordCounter, self).__setitem__(key, value)

    def most_common(self, n: int | None = None) -> List[Tuple[str, int]]:
        if n is None:
            return sorted(iter(self.items()), key=itemgetter(1), reverse=True)
        return nlargest(n, iter(self.items()), key=itemgetter(1))


class WordAndAttributeCounter():

    def __init__(self, stopwords: FrozenSet = STOPWORDS) -> None:
        self.counter: Dict[str, WordAttributeCount] = defaultdict(WordAttributeCount)
        self.stopwords: FrozenSet = stopwords

    def add(self, word: str, attribute: str) -> None:
        if word not in self.stopwords and len(word) > 2:
            self.counter[word].add(attribute)

    def most_common(self, n: int | None = None) -> List[Tuple[str, "WordAttributeCount"]]:
        if n is None:
            return sorted(iter(self.counter.items()), key=lambda x: x[1].count, reverse=True)
        return nlargest(n, iter(self.counter.items()), key=lambda x: x[1].count)


class WordAttributeCount():

    __slots__ = ('count', 'attributes')

    def __init__(self) -> None:
        self.attributes: Dict[str, int] = defaultdict(int)
        self.count: int = 0

    def add(self, attribute: str) -> None:
        self.attributes[attribute] += 1
        self.count += 1

    def winning_attribute(self) -> str:
        return nlargest(1, iter(self.attributes.items()), key=itemgetter(1))[0][0]
