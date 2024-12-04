import json
import re
from http import HTTPStatus
from typing import Any, override

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.views.generic import View


class JSONView(View):
    """Base view that serializes responses as JSON."""

    # Subclasses: set this to True to allow JSONP (cross-domain) requests
    allow_jsonp = False

    wrap = True

    def __init__(self) -> None:
        super(JSONView, self).__init__()
        self.content_type = 'application/json'

    @override
    def dispatch(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        result = super(JSONView, self).dispatch(request, *args, **kwargs)
        indent_response = 4 if request.GET.get('indent') else None

        if isinstance(result, HttpResponse):
            return result
        resp = HttpResponse(content_type=self.content_type)
        callback = ''
        if self.allow_jsonp and 'callback' in request.GET:
            callback = re.sub(r'[^a-zA-Z0-9_]', '', request.GET['callback'])
            resp.write(callback + '(')
        if self.wrap:
            result = HttpResponse(content=result, status=HTTPStatus.OK)
        json.dump(result, resp, indent=indent_response)
        if callback:
            resp.write(');')

        return resp

    def redirect(self, url: str) -> HttpResponse:
        return AjaxRedirectResponse(url)


class AjaxRedirectResponse(HttpResponse):

    def __init__(self, url: str, status_code: int = HTTPStatus.FORBIDDEN) -> None:
        super(AjaxRedirectResponse, self).__init__(
            '<script>window.location.href = "%s";</script>' % url,
            content_type='text/html'
        )
        self.status_code = status_code
        self['X-OP-Redirect'] = url


def adaptive_redirect(request: HttpRequest, url: str) -> HttpResponse:
    if 'XMLHttpRequest' in request.headers.get('X-Requested-With', ''):
        return AjaxRedirectResponse(url)
    return HttpResponseRedirect(url)
