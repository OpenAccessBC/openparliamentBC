from typing import Any, override

from django.db import models

from parliament.core.models import Politician
from parliament.core.utils import ActiveManager


class Activity(models.Model):

    date: models.DateField = models.DateField(db_index=True)
    variety: models.CharField = models.CharField(max_length=15)
    politician: models.ForeignKey = models.ForeignKey(Politician, on_delete=models.CASCADE)
    payload: models.TextField = models.TextField()
    guid: models.CharField = models.CharField(max_length=50, db_index=True, unique=True)
    active: models.BooleanField = models.BooleanField(default=True, db_index=True)

    objects = models.Manager()
    public = ActiveManager()

    class Meta:
        ordering = ('-date', '-id')
        verbose_name_plural = 'Activities'

    def payload_wrapped(self):
        return '<p class="activity_item" data-id="%s">%s</p>' % (self.pk, self.payload)

    @override
    def save(self, *args: Any, **kwargs: Any) -> None:
        self.full_clean()
        super(Activity, self).save(*args, **kwargs)
