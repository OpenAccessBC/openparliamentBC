from django.contrib import admin

from parliament.bills.models import Bill, BillEvent, BillInSession, BillText, MemberVote, PartyVote, VoteQuestion


class BillOptions(admin.ModelAdmin[Bill]):
    search_fields = ['number']
    raw_id_fields = ['sponsor_member', 'sponsor_politician']
    list_display = ['number', 'name', 'session', 'privatemember', 'sponsor_politician', 'added', 'introduced']
    list_filter = ['institution', 'privatemember', 'added', 'sessions', 'introduced', 'status_date']
    ordering = ['-introduced']


class BillInSessionOptions(admin.ModelAdmin[BillInSession]):
    list_display = ['bill', 'session']


class BillTextOptions(admin.ModelAdmin[BillText]):
    list_display = ['bill', 'docid', 'created']
    search_fields = ['bill__number', 'bill__name_en', 'docid']


class VoteQuestionOptions(admin.ModelAdmin[VoteQuestion]):
    list_display = ['number', 'date', 'bill', 'description', 'result']
    raw_id_fields = ['bill', 'context_statement']


class MemberVoteOptions(admin.ModelAdmin[MemberVote]):
    list_display = ['politician', 'votequestion', 'vote']
    raw_id_fields = ['politician', 'member']


class PartyVoteAdmin(admin.ModelAdmin[PartyVote]):
    list_display = ['party', 'votequestion', 'vote', 'disagreement']


class BillEventAdmin(admin.ModelAdmin[BillEvent]):
    list_display = ['bill_number', 'status', 'date', 'institution']
    raw_id_fields = ['debate', 'committee_meetings', 'bis']
    list_filter = ['date', 'institution']


admin.site.register(Bill, BillOptions)
admin.site.register(BillInSession, BillInSessionOptions)
admin.site.register(BillText, BillTextOptions)
admin.site.register(VoteQuestion, VoteQuestionOptions)
admin.site.register(MemberVote, MemberVoteOptions)
admin.site.register(PartyVote, PartyVoteAdmin)
admin.site.register(BillEvent, BillEventAdmin)
