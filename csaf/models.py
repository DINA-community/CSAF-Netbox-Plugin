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
        max_length=1000,
        blank=False,
        null=False
    )
    docurl = models.CharField(
        max_length=1000,
        blank=False,
        null=False,
        unique=True
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
    product_tree = models.JSONField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = ['id']
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
    class AcceptanceStatus(models.TextChoices):
        NEW = "N", "New"
        REOPENED = "O", "Reopened"
        CONFIRMED = "C", "Confirmed"
        FALSE_POSITIVE = "F", "False Positive"

    class RemediationStatus(models.TextChoices):
        NEW = "1", "Not Started"
        IN_PROGRESS = "2", "In Progress"
        RESOLVED = "3", "Complete"


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
    module = models.ForeignKey(
        to='dcim.Module',
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
    product_name_id = models.CharField(
        blank=False,
        null=False,
        default='unknown'
    )
    score = models.FloatField(default=0.0)
    time = models.DateTimeField(default=timezone.now)
    acceptance_status = models.CharField(
        max_length=1,
        choices=AcceptanceStatus,
        default=AcceptanceStatus.NEW,
    )
    remediation_status = models.CharField(
        max_length=1,
        choices=RemediationStatus,
        default=RemediationStatus.NEW,
    )
    description = models.TextField(
        blank=True,
        null=True
    )

    class Meta:
        ordering = ['id']
        verbose_name_plural = 'CsafMatches'
        constraints = [
            models.UniqueConstraint(
                fields=["device", "software", "csaf_document", "product_name_id"],
                name="csafmatch_unique",
                nulls_distinct=False)
        ]

    @property
    def docs_url(self):
        return None

    @property
    def related_vulnerabilities(self):
        """
        Return only vulnerabilities relevant for this match's product identifier.
        """
        product_id = (self.product_name_id or '').strip()
        vulnerabilities = self.csaf_document.vulnerabilities.all()
        if not product_id:
            return []
        return [v for v in vulnerabilities if v.matches_product_id(product_id)]


class CsafVulnerability(NetBoxModel):
    """
    A CsafVulnerability instance represents one vulnerability entry of a CSAF document.
    """
    csaf_document = models.ForeignKey(
        to='csaf.CsafDocument',
        on_delete=models.CASCADE,
        related_name='vulnerabilities',
    )
    ordinal = models.PositiveIntegerField()
    vulnerability_id = models.CharField(
        max_length=255,
        blank=False,
        null=False,
    )
    cve = models.CharField(
        max_length=100,
        blank=True,
        null=True,
    )
    title = models.CharField(
        max_length=1000,
        blank=True,
        null=True,
    )
    summary = models.TextField(
        blank=True,
        null=True,
    )
    cwe = models.CharField(
        max_length=255,
        blank=True,
        null=True,
    )
    cvss_base_score = models.FloatField(
        blank=True,
        null=True,
    )
    product_ids = models.JSONField(
        blank=True,
        default=list,
    )

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['csaf_document', 'ordinal'],
                name='csafvulnerability_unique_ordinal_per_doc',
            )
        ]

    def __str__(self):
        return self.vulnerability_id

    def matches_product_id(self, product_id):
        if not product_id:
            return False
        return product_id in (self.product_ids or [])
