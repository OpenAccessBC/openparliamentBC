import datetime
import re

from django import http
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def memcached_status(request: HttpRequest) -> HttpResponse:

    try:
        import memcache
    except ImportError:
        raise http.Http404 from None

    if not (request.user.is_authenticated and request.user.is_staff):
        raise http.Http404

    # get first memcached URI
    m = re.match(
        r"memcached://([.\w]+:\d+)", settings.CACHE_BACKEND
    )
    if not m:
        raise http.Http404

    host = memcache._Host(m.group(1))
    host.connect()
    host.send_cmd("stats")

    class Stats:
        pass

    stats = Stats()

    while 1:
        line = host.readline().split(None, 2)
        if line[0] == "END":
            break
        _, key, value = line
        try:
            # convert to native type, if possible
            value = int(value)
            if key == "uptime":
                value = datetime.timedelta(seconds=value)
            elif key == "time":
                value = datetime.datetime.fromtimestamp(value)
        except ValueError:
            pass
        setattr(stats, key, value)

    host.close_socket()

    return render(
        request,
        'memcached_status.html',
        {
            "stats": stats,
            "hit_rate": 100 * stats.get_hits / stats.cmd_get,
            "time": datetime.datetime.now(),  # server time
        })
