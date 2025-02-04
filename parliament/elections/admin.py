from django.contrib import admin

from parliament.elections.models import Candidacy, Election


class CandidacyOptions(admin.ModelAdmin[Candidacy]):

    list_display = ['candidate', 'riding', 'party', 'election', 'elected', 'votepercent']
    search_fields = ['candidate__name', 'riding__name_en', 'party__name_en']
    list_filter = ['party', 'election', 'elected']


admin.site.register(Election)
admin.site.register(Candidacy, CandidacyOptions)
