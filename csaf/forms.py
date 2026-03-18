"""
    This file provides all the input forms implemented by the CSAF-Plugin.
"""

import datetime
from .models import CsafDocument, CsafMatch, CsafVulnerability
from dcim.models.devices import Device, Module
from django import forms
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm, NetBoxModelBulkEditForm
from utilities.forms.fields import DynamicModelMultipleChoiceField
from django.contrib.postgres.forms import SimpleArrayField
from d3c.models import Software


class CsafDocumentForm(NetBoxModelForm):
    """
    Input Form for the CsafDocument model.
    """
    class Meta:
        model = CsafDocument
        fields = ('id', 'title', 'docurl', 'version', 'lang', 'publisher')


class CsafDocumentFilterForm(NetBoxModelFilterSetForm):
    """
    Input Form for filtering CsafDocument objects.
    """
    model = CsafDocument
    title = forms.CharField(required=False)
    docurl = forms.CharField(required=False)
    version = forms.CharField(required=False)
    lang = forms.CharField(required=False)
    publisher = forms.CharField(required=False)


class CsafDocumentSearchForm(forms.Form):
    """
    Input form for searching CSAF documents by name/title in ISDuBA.
    """
    q = forms.CharField(required=False, label='Document name')
    selected_docurls = forms.MultipleChoiceField(
        required=False,
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label='Matching documents',
    )


class CsafMatchForm(NetBoxModelForm):
    """
    Input Form for the CsafMatch model.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device', 'module', 'software', 'csaf_document', 'score', 'time', 'acceptance_status', 'description', 'product_name_id')


class CsafMatchFilterForm(NetBoxModelFilterSetForm):
    """
    Input Form for filtering CsafMatch objects.
    """
    model = CsafMatch
    device_id = DynamicModelMultipleChoiceField(
        queryset = Device.objects.all(),
        required = False,
        label = 'Device',
    )
    module_id = DynamicModelMultipleChoiceField(
        queryset = Module.objects.all(),
        required = False,
        label = 'Module',
    )
    software_id = DynamicModelMultipleChoiceField(
        queryset = Software.objects.all(),
        required = False,
        label = 'Software',
    )
    csaf_document_id = DynamicModelMultipleChoiceField(
        queryset = CsafDocument.objects.all(),
        required = False,
        label = 'CSAF Document',
    )
    minscore = forms.DecimalField(
        required = False,
        label = 'Minimum Score',
    )
    maxscore = forms.DecimalField(
        required = False,
        label = 'Maximum Score',
    )
    description = forms.CharField(required=False)


class CsafMatchBulkEditForm(NetBoxModelBulkEditForm):
    model = CsafMatch
    acceptance_status = forms.ChoiceField(
        choices=CsafMatch.AcceptanceStatus,
        required=False
    )
    remediation_status = forms.ChoiceField(
        choices=CsafMatch.RemediationStatus,
        required=False
    )


class CsafVulnerabilityForm(NetBoxModelForm):
    """
    Input Form for the CsafVulnerability model.
    """
    class Meta:
        model = CsafVulnerability
        fields = ('id', 'csaf_document', 'ordinal', 'vulnerability_id', 'cve', 'title', 'summary', 'cwe', 'cvss_base_score', 'product_ids')


class CsafVulnerabilityFilterForm(NetBoxModelFilterSetForm):
    """
    Input Form for filtering CsafVulnerability objects.
    """
    model = CsafVulnerability
    csaf_document_id = DynamicModelMultipleChoiceField(
        queryset=CsafDocument.objects.all(),
        required=False,
        label='CSAF Document',
    )
    vulnerability_id = forms.CharField(required=False)
    cve = forms.CharField(required=False)
    title = forms.CharField(required=False)
    cwe = forms.CharField(required=False)
