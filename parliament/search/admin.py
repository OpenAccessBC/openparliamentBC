from django.contrib import admin

from parliament.search.models import IndexingTask


class IndexingTaskAdmin(admin.ModelAdmin[IndexingTask]):

    list_display = ['action', 'identifier', 'timestamp', ]  # 'content_object']
    list_filter = ['action', 'timestamp']


admin.site.register(IndexingTask, IndexingTaskAdmin)
