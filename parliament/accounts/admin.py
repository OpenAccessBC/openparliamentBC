from django.contrib import admin

from parliament.accounts.models import LoginToken, User


class UserAdmin(admin.ModelAdmin[User]):

    list_display = ['email', 'name', 'created', 'last_login', 'email_bouncing']
    search_fields = ['email']
    list_filter = ['last_login', 'created', 'email_bouncing']


class LoginTokenAdmin(admin.ModelAdmin[LoginToken]):
    list_display = ['token', 'email', 'used', 'created', 'requesting_ip', 'login_ip']
    search_fields = ['token', 'email']
    ordering = ['-created']


admin.site.register(User, UserAdmin)
admin.site.register(LoginToken, LoginTokenAdmin)
