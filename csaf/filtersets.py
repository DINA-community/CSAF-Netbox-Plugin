import django_filters
from dcim.models.devices import Device, Module
from django import forms
from django_filters import NumberFilter
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filters import MultiValueCharFilter
from d3c.models import Software
from .models import CsafDocument, CsafMatch, CsafVulnerability, CsafMatchVulnerabilityRemediation


class CsafDocumentFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafDocument.
    """
    title = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    tracking_id = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    docurl = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    version = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    lang = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    publisher = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    class Meta:
        model = CsafDocument
        fields = ('id', 'title', 'tracking_id', 'docurl', 'version', 'lang', 'publisher')

    def search(self, queryset, title, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(title__icontains=value) |
            Q(tracking_id__icontains=value)
        )


class CsafMatchFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafMatch.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device_id', 'module_id', 'software_id', 'csaf_document_id', 'acceptance_status', 'remediation_status')

    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset = Device.objects.all(),
        label = 'Devices',
    )

    module_id = django_filters.ModelMultipleChoiceFilter(
        queryset = Module.objects.all(),
        label = 'Modules',
    )

    software_id = django_filters.ModelMultipleChoiceFilter(
        queryset = Software.objects.all(),
        label = 'Software',
    )

    csaf_document_id = django_filters.ModelMultipleChoiceFilter(
        queryset = CsafDocument.objects.all(),
        label = 'Documents',
    )
    minscore = NumberFilter(
        field_name='score',
        lookup_expr='gte',
    )
    maxscore = NumberFilter(
        field_name='score',
        lookup_expr='lte',
    )

    acceptance_status = django_filters.MultipleChoiceFilter(
        choices=CsafMatch.AcceptanceStatus,
        null_value=None
    )

    remediation_status = django_filters.MultipleChoiceFilter(
        choices=CsafMatch.RemediationStatus,
        null_value=None
    )

    def search(self, queryset, status, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(description__icontains=value) |
            Q(csaf_document__title__icontains=value) |
            Q(csaf_document__tracking_id__icontains=value) |
            Q(software__name__icontains=value) |
            Q(device__name__icontains=value) |
            Q(module__name__icontains=value)
        )


class CsafVulnerabilityFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafVulnerability.
    """
    class Meta:
        model = CsafVulnerability
        fields = ('id', 'csaf_document_id', 'vulnerability_id', 'cve', 'title', 'cwe')

    csaf_document_id = django_filters.ModelMultipleChoiceFilter(
        queryset=CsafDocument.objects.all(),
        label='Documents',
    )

    vulnerability_id = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    cve = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    title = MultiValueCharFilter(
        lookup_expr='icontains'
    )
    cwe = MultiValueCharFilter(
        lookup_expr='icontains'
    )

    def search(self, queryset, status, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(vulnerability_id__icontains=value) |
            Q(cve__icontains=value) |
            Q(title__icontains=value) |
            Q(summary__icontains=value) |
            Q(cwe__icontains=value) |
            Q(csaf_document__title__icontains=value) |
            Q(csaf_document__tracking_id__icontains=value)
        )

class CsafMatchVulnerabilityRemediationFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafMatchVulnerabilityRemediation.
    """
    class Meta:
        model = CsafMatchVulnerabilityRemediation
        fields = ('id', 'match_id', 'vulnerability_id', 'csaf_document_id', 'remediation_status')

    vulnerability_id = django_filters.ModelMultipleChoiceFilter(
        queryset=CsafVulnerability.objects.all(),
        label='Vulnerability',
    )

    csaf_document_id = django_filters.ModelMultipleChoiceFilter(
        queryset=CsafDocument.objects.all(),
        label='Document',
        field_name='vulnerability__csaf_document_id',
    )

    cve = MultiValueCharFilter(
        label='Vulnerability CVE',
        field_name='vulnerability__cve',
        lookup_expr='icontains'
    )
    title = MultiValueCharFilter(
        label='Vulnerability Title',
        field_name='vulnerability__title',
        lookup_expr='icontains'
    )
    cwe = MultiValueCharFilter(
        label='Vulnerability CWE',
        field_name='vulnerability__cwe',
        lookup_expr='icontains'
    )

    def search(self, queryset, status, value):
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(vulnerability__cve__icontains=value)
            | Q(vulnerability__title__icontains=value)
            | Q(vulnerability__summary__icontains=value)
            | Q(vulnerability__cwe__icontains=value)
            | Q(vulnerability__csaf_document__title__icontains=value)
            | Q(vulnerability__csaf_document__tracking_id__icontains=value)
        )
