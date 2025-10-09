from django.db import models
from django.urls import reverse
from django.utils import timezone
from netbox.models import NetBoxModel

class CsafDocument(NetBoxModel):
    """
    A CsafDocument instance represents a reference to a CSAF advisory document.
    The document itself is available somewhere else, for instance in an IsDuBa cache.
    Only the main fields are represented here.
    """
    title = models.CharField(
        max_length=100,
        blank=False,
        null=False
    )
    docurl = models.CharField(
        max_length=1000,
        blank=False,
        null=False
    )
    version = models.CharField(
        max_length=50,
        blank=True,
        null=True
    )
    lang = models.CharField(
        max_length=20,
        blank=True,
        null=True
    )
    publisher = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )

    def get_absolute_url(self):
        return reverse('plugins:csaf:csafdocument', args=[self.pk])

    class Meta:
        verbose_name_plural = 'CsafDocuments'

    def __str__(self):
        return self.title

    @property
    def docs_url(self):
        return None


class CsafMatch(NetBoxModel):
    """
    A CsafMatch instance links a CSAF advisory to an asset.
    """
    class Status(models.TextChoices):
        NEW = "N", "New"
        CONFIRMED = "C", "Confirmed"
        RESOLVED = "R", "Resolved"
        FALSE_POSITIVE = "F", "False Positive"


    device = models.ForeignKey(
        to='dcim.Device',
        on_delete=models.SET_NULL,
        related_name='csaf_matches',
        blank=True,
        null=True
    )
    software = models.ForeignKey(
        to='d3c.Software',
        on_delete=models.CASCADE,
        related_name='csaf_matches',
        blank=True,
        null=True
    )
    csaf_document = models.ForeignKey(
        to='csaf.CsafDocument',
        on_delete=models.CASCADE,
        related_name='csaf_matches',
    )
    score = models.FloatField(default=0.0)
    time = models.DateTimeField(default=timezone.now)
    status = models.CharField(
        max_length=1,
        choices=Status,
        default=Status.NEW,
    )
    description = models.CharField(
        blank=True,
        null=True
    )
    def get_absolute_url(self):
        return reverse('plugins:csaf:csafmatch', args=[self.pk])

    class Meta:
        verbose_name_plural = 'CsafMatches'

    @property
    def docs_url(self):
        return None
