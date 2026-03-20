from django.db import models
from django.urls import reverse
from django.utils.html import format_html
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
    tracking_id = models.CharField(
        max_length=255,
        blank=True,
        null=True
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

    @property
    def related_vulnerability_entries(self):
        status_map = self.vulnerability_remediation_map
        entries = []
        for vulnerability in self.related_vulnerabilities:
            status_value = status_map.get(vulnerability.id, self.RemediationStatus.NEW)
            status_label = self.RemediationStatus(status_value).label
            entries.append({
                'vulnerability': vulnerability,
                'status_value': status_value,
                'status_label': status_label,
            })
        return entries

    @property
    def related_asset(self):
        """
        Resolve this match to the associated NetBox asset object.
        """
        if self.device is not None:
            return self.device
        if self.module is not None:
            return self.module
        if self.software is not None:
            return self.software
        return None

    @property
    def related_asset_type(self):
        if self.device is not None:
            return 'Device'
        if self.module is not None:
            return 'Module'
        if self.software is not None:
            return 'Software'
        return '-'

    @property
    def remediation_status_choices(self):
        return self.RemediationStatus

    @property
    def vulnerability_remediations(self):
        return self.vulnerability_statuses.select_related('vulnerability').order_by('vulnerability__ordinal')

    @property
    def vulnerability_remediation_map(self):
        return {
            entry.vulnerability_id: entry.remediation_status
            for entry in self.vulnerability_statuses.all()
        }

    def get_vulnerability_remediation_status(self, vulnerability):
        return self.vulnerability_remediation_map.get(vulnerability.id, self.RemediationStatus.NEW)

    def sync_vulnerability_remediations(self):
        vulnerabilities = list(self.related_vulnerabilities)
        vulnerability_ids = [v.id for v in vulnerabilities]

        existing = {
            entry.vulnerability_id: entry
            for entry in self.vulnerability_statuses.all()
        }

        for vulnerability in vulnerabilities:
            if vulnerability.id not in existing:
                CsafMatchVulnerabilityRemediation.objects.create(
                    match=self,
                    vulnerability=vulnerability,
                    remediation_status=self.RemediationStatus.NEW,
                )

        self.vulnerability_statuses.exclude(vulnerability_id__in=vulnerability_ids).delete()
        self.update_remediation_from_vulnerabilities()

    def update_remediation_from_vulnerabilities(self):
        statuses = list(self.vulnerability_statuses.values_list('remediation_status', flat=True))
        if not statuses:
            target_status = self.RemediationStatus.NEW
        elif all(status == self.RemediationStatus.RESOLVED for status in statuses):
            target_status = self.RemediationStatus.RESOLVED
        elif any(status in (self.RemediationStatus.IN_PROGRESS, self.RemediationStatus.RESOLVED) for status in statuses):
            target_status = self.RemediationStatus.IN_PROGRESS
        else:
            target_status = self.RemediationStatus.NEW

        if self.remediation_status != target_status:
            self.remediation_status = target_status
            self.__class__.objects.filter(pk=self.pk).update(remediation_status=target_status)

    def set_all_vulnerability_remediations(self, remediation_status):
        self.sync_vulnerability_remediations()
        self.vulnerability_statuses.update(remediation_status=remediation_status)
        self.update_remediation_from_vulnerabilities()

    def set_vulnerability_remediation(self, vulnerability, remediation_status):
        self.sync_vulnerability_remediations()
        entry, _ = CsafMatchVulnerabilityRemediation.objects.get_or_create(
            match=self,
            vulnerability=vulnerability,
            defaults={'remediation_status': remediation_status},
        )
        if entry.remediation_status != remediation_status:
            entry.remediation_status = remediation_status
            entry.save(update_fields=['remediation_status'])
        self.update_remediation_from_vulnerabilities()

    @property
    def remediation_progress(self):
        statuses = list(self.vulnerability_statuses.values_list('remediation_status', flat=True))
        total = len(statuses)
        resolved = sum(1 for status in statuses if status == self.RemediationStatus.RESOLVED)
        in_progress = sum(1 for status in statuses if status == self.RemediationStatus.IN_PROGRESS)
        resolved_percentage = int((resolved * 100) / total) if total else 0
        in_progress_percentage = int((in_progress * 100) / total) if total else 0
        return {
            'resolved': resolved,
            'in_progress': in_progress,
            'total': total,
            'resolved_percentage': resolved_percentage,
            'in_progress_percentage': in_progress_percentage,
        }


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

    @property
    def cvss_severity(self):
        score = self.cvss_base_score
        if score is None:
            return None
        if score == 0:
            return 'None'
        if score < 4.0:
            return 'Low'
        if score < 7.0:
            return 'Medium'
        if score < 9.0:
            return 'High'
        return 'Critical'

    @property
    def cvss_badge(self):
        score = self.cvss_base_score
        severity = self.cvss_severity
        if score is None or severity is None:
            return '-'
        try:
            score_value = float(score)
        except (TypeError, ValueError):
            return '-'

        class_name = {
            'None': 'text-bg-secondary',
            'Low': 'text-bg-success',
            'Medium': 'text-bg-warning',
            'High': 'text-bg-danger',
            'Critical': 'text-bg-danger',
        }.get(severity, 'text-bg-secondary')

        return format_html(
            '<span class="badge {}">{} ({})</span>',
            class_name,
            f'{score_value:.1f}',
            severity,
        )

    @property
    def related_matches(self):
        product_ids = self.product_ids or []
        if not product_ids:
            return CsafMatch.objects.none()
        return CsafMatch.objects.filter(
            csaf_document=self.csaf_document,
            product_name_id__in=product_ids,
        ).select_related('device', 'module', 'software', 'csaf_document')


class CsafMatchVulnerabilityRemediation(NetBoxModel):
    """
    Remediation state of a specific vulnerability on a specific match/asset.
    """
    match = models.ForeignKey(
        to='csaf.CsafMatch',
        on_delete=models.CASCADE,
        related_name='vulnerability_statuses',
    )
    vulnerability = models.ForeignKey(
        to='csaf.CsafVulnerability',
        on_delete=models.CASCADE,
        related_name='match_statuses',
    )
    remediation_status = models.CharField(
        max_length=1,
        choices=CsafMatch.RemediationStatus,
        default=CsafMatch.RemediationStatus.NEW,
    )

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['match', 'vulnerability'],
                name='csafmatchvulnremediation_unique',
            )
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.match.update_remediation_from_vulnerabilities()

    def delete(self, *args, **kwargs):
        match = self.match
        super().delete(*args, **kwargs)
        match.update_remediation_from_vulnerabilities()
