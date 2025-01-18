from typing import Any, override

from django.contrib import admin
from django.db.models import ForeignKey
from django.http import HttpRequest

from parliament.core.models import ElectedMember, InternalXref, Party, Politician, PoliticianInfo, Riding, Session, SiteNews, models


class PoliticianInfoInline(admin.TabularInline[PoliticianInfo, PoliticianInfo]):
    model = PoliticianInfo


class PoliticianOptions(admin.ModelAdmin[Politician]):
    inlines = [PoliticianInfoInline]
    search_fields = ['name']


class RidingOptions(admin.ModelAdmin[Riding]):
    list_display = ['name_en', 'current', 'province', 'edid', 'name_fr']
    search_fields = ['name_en', 'edid']
    list_filter = ['province', 'current']


class SessionOptions(admin.ModelAdmin[Session]):
    list_display = ['name', 'start', 'end']


class ElectedMemberOptions(admin.ModelAdmin[ElectedMember]):
    list_display = ['politician', 'riding', 'party', 'start_date', 'end_date']
    list_filter = ['party']
    search_fields = ['politician__name']


class InternalXrefOptions(admin.ModelAdmin[InternalXref]):
    list_display = ['schema', 'text_value', 'int_value', 'target_id']
    search_fields = ['schema', 'text_value', 'int_value', 'target_id']
    list_editable = ['text_value', 'int_value', 'target_id']


class PartyOptions(admin.ModelAdmin[Party]):
    list_display = ['name_en', 'short_name', 'name_fr', 'short_name_fr']


class PoliticianInfoOptions(admin.ModelAdmin[PoliticianInfo]):
    list_display = ['politician', 'schema', 'value']
    search_fields = ['politician__name', 'schema', 'value']

    # FIXME: Should return `Field | None`
    @override
    def formfield_for_foreignkey(self, db_field: ForeignKey, request: HttpRequest, **kwargs: Any) -> Any:
        if db_field.name == "politician":
            kwargs["queryset"] = Politician.objects.elected()
            return db_field.formfield(**kwargs)
        return super(admin.ModelAdmin[PoliticianInfo], self).formfield_for_foreignkey(db_field, request, **kwargs, on_delete=models.CASCADE)


class SiteNewsOptions(admin.ModelAdmin[SiteNews]):
    list_display = ['title', 'date', 'active']


admin.site.register(ElectedMember, ElectedMemberOptions)
admin.site.register(Riding, RidingOptions)
admin.site.register(Session, SessionOptions)
admin.site.register(Politician, PoliticianOptions)
admin.site.register(Party, PartyOptions)
admin.site.register(InternalXref, InternalXrefOptions)
admin.site.register(PoliticianInfo, PoliticianInfoOptions)
admin.site.register(SiteNews, SiteNewsOptions)
