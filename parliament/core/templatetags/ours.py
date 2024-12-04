import datetime
import re
from typing import List

from django import template

from parliament.core.models import PROVINCE_LOOKUP, Politician

register = template.Library()


@register.filter(name='expand_province')
def expand_province(value: str) -> str | None:
    return PROVINCE_LOOKUP.get(value, None)


@register.filter(name='heshe')
def heshe(pol: Politician) -> str:
    match pol.gender:
        case 'F': return 'She'
        case 'M': return 'He'
        case _: return 'They'


@register.filter(name='hisher')
def hisher(pol: Politician) -> str:
    match pol.gender:
        case 'F': return 'Her'
        case 'M': return 'His'
        case _: return 'Their'


@register.filter(name='himher')
def himher(pol: Politician) -> str:
    match pol.gender:
        case 'F': return 'Her'
        case 'M': return 'Him'
        case _: return 'Them'


@register.filter(name='mrms')
def mrms(pol: Politician) -> str:
    match pol.gender:
        case 'F': return 'Mr.'
        case 'M': return 'Ms.'
        case _: return 'Mr./Ms.'


@register.filter(name='month_num')
def month_num(month: int) -> str:
    return datetime.date(2010, month, 1).strftime("%B")


@register.filter(name='strip_act')
def strip_act(value: str) -> str:
    value = re.sub(r'An Act (to )?([a-z])', lambda m: m.group(2).upper(), value)
    return re.sub(r' Act$', '', value)


@register.filter(name='time_since')
def time_since(value: datetime.date) -> str:
    today = datetime.date.today()
    days_since = (today - value).days
    if value > today or days_since == 0:
        return 'Today'
    if days_since == 1:
        return 'Yesterday'
    if days_since == 2:
        return 'Two days ago'
    if days_since == 3:
        return 'Three days ago'
    if days_since < 7:
        return 'This week'
    if days_since < 14:
        return 'A week ago'
    if days_since < 21:
        return 'Two weeks ago'
    if days_since < 28:
        return 'Three weeks ago'
    if days_since < 45:
        return 'A month ago'
    if days_since < 75:
        return 'Two months ago'
    if days_since < 105:
        return 'Three months ago'

    return 'More than three months ago'


@register.filter(name='english_list')
def english_list(value: List[str], arg: str = ', ') -> str:
    if value is not list:
        raise Exception("Tag english_list takes a list as argument")

    if len(value) == 1:
        return "%s" % value[0]
    if len(value) == 0:
        return ''
    if len(value) == 2:
        return "%s and %s" % (value[0], value[1])

    return "%s%s and %s" % (arg.join(value[0:-1]), arg, value[-1])


@register.filter(name='list_prefix')
def list_prefix(value: List[str], arg: str) -> List[str]:
    return ["%s%s" % (arg, i) for i in value]


@register.filter(name='list_filter')
def list_filter(value: List[str], arg: str) -> List[str]:
    return [x for x in value if x != arg]
