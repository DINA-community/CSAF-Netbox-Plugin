"""
    This file provides all the input forms implemented by the CSAF-Plugin.
"""

import datetime
from .models import CsafDocument, CsafMatch
from dcim.models.devices import Device
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


class CsafMatchForm(NetBoxModelForm):
    """
    Input Form for the CsafMatch model.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')


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
    status = forms.ChoiceField(
        choices=CsafMatch.Status,
        required=False
    )
