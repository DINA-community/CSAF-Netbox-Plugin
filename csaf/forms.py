"""
    This file provides all the input forms implemented by the CSAF-Plugin.
"""

from .models import CsafDocument, CsafMatch
from dcim.models.devices import Device
from django import forms
from netbox.forms import NetBoxModelForm, NetBoxModelFilterSetForm
from utilities.forms.fields import DynamicModelMultipleChoiceField
from django.contrib.postgres.forms import SimpleArrayField


class CsafDocumentForm(NetBoxModelForm):
    """
    Input Form for the CsafDocument model.
    """
    class Meta:
        model = CsafDocument
        fields = ('id', 'title', 'url', 'version', 'lang', 'publisher')


class CsafDocumentFilterForm(NetBoxModelFilterSetForm):
    """
    Input Form for filtering CsafDocument objects.
    """
    model = CsafDocument
    title = forms.CharField(required=False)
    url = forms.BooleanField(required=False)
    publisher = forms.CharField(required=False)

