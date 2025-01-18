from django.conf import settings
from django.http import HttpRequest
from django.template import loader


def server_error(request: HttpRequest, template_name: str = '500.html'):
    "Always includes MEDIA_URL"
    from django.http import HttpResponseServerError
    t = loader.get_template(template_name)
    return HttpResponseServerError(t.render({
        'MEDIA_URL': settings.MEDIA_URL,
        'STATIC_URL': settings.STATIC_URL
    }))
