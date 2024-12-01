from typing import List, Tuple
from urllib.parse import urljoin

import lxml.etree
import lxml.html
import requests


def get_bill_text_xml(bill_or_url):
    """Given a Bill object or URL to a full-text page on ourcommons.ca,
    returns an lxml Element object for the container div of the full
    bill text."""

    if hasattr(bill_or_url, 'get_billtext_url'):
        bill_or_url = bill_or_url.get_billtext_url()

    resp = requests.get(bill_or_url, timeout=10)
    html_root = lxml.html.fromstring(resp.content)
    xml_button = html_root.cssselect('a.btn-export-xml')
    xml_url = urljoin(bill_or_url, xml_button[0].get('href'))

    resp2 = requests.get(xml_url, timeout=10)
    return lxml.etree.fromstring(resp2.content)


def get_plain_bill_text(bill_or_url) -> Tuple[str, str]:
    bill_el = get_bill_text_xml(bill_or_url)
    body = bill_el.xpath('//Body')[0]
    return get_bill_summary(bill_el), ' '.join(body.itertext())


def get_bill_summary(bill_el) -> str:
    summary = bill_el.xpath('//Summary')[0]
    texts = []

    def _descend(tag):
        if tag.tag == 'TitleText':
            return
        if tag.tag == 'Provision':
            texts.append('\n')
        if tag.text:
            texts.append(tag.text.replace('\n', ''))
        for sub in tag.iterchildren():
            _descend(sub)
        if tag.tail:
            texts.append(tag.tail.replace('\n', ''))
    _descend(summary)
    return (' '.join(texts)).strip()
