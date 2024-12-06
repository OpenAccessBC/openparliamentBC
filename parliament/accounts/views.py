from typing import Any

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import reverse
from django.views.decorators.cache import never_cache

from parliament.accounts.models import LoginToken, TokenError, User
from parliament.core.views import disable_on_readonly_db
from parliament.utils.views import JSONView


class CurrentAccountView(JSONView):

    def get(self, request: HttpRequest) -> dict[str, Any]:
        return {'email': request.authenticated_email}


current_account = never_cache(CurrentAccountView.as_view())


class LogoutView(JSONView):

    def post(self, request: HttpRequest) -> bool:
        request.authenticated_email = None
        return True


logout = never_cache(LogoutView.as_view())


def _get_ip(request: HttpRequest) -> str:
    ip = request.META['REMOTE_ADDR']
    if ip == '127.0.0.1' and 'HTTP_X_REAL_IP' in request.META:
        ip = request.META['HTTP_X_REAL_IP']
    return ip


class LoginTokenCreateView(JSONView):

    def post(self, request: HttpRequest) -> HttpResponse | str:
        email = request.POST.get('email').lower().strip()
        try:
            EmailValidator()(email)
        except ValidationError as e:
            return HttpResponse(e.message, content_type='text/plain', status=400)
        LoginToken.generate(
            email=email,
            requesting_ip=_get_ip(request)
        )
        return 'sent'


create_token = disable_on_readonly_db(LoginTokenCreateView.as_view())


@never_cache
@disable_on_readonly_db
def token_login(request: HttpRequest, token: str) -> HttpResponse:
    if request.method != 'GET':
        # Some email systems make HEAD requests to all URLs
        return HttpResponseNotAllowed(['GET'])

    redirect_url = reverse('alerts_list')

    try:
        lt = LoginToken.validate(token=token, login_ip=_get_ip(request))
    except TokenError as e:
        messages.error(request, str(e))
        return HttpResponseRedirect(redirect_url)

    user, _ = User.objects.get_or_create(email=lt.email)
    user.log_in(request)

    if lt.post_login_url:
        redirect_url = lt.post_login_url
    return HttpResponseRedirect(redirect_url)
