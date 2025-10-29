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
    docurl = forms.BooleanField(required=False)
    publisher = forms.CharField(required=False)


class CsafMatchForm(NetBoxModelForm):
    """
    Input Form for the CsafMatch model.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')


class CsafMatchBulkEditForm(NetBoxModelBulkEditForm):
    model = CsafMatch
    status = forms.ChoiceField(
        choices=CsafMatch.Status,
        required=False
    )
