import django_filters
from django import forms
from django.db.models import Q
from netbox.forms import NetBoxModelFilterSetForm
from netbox.filtersets import NetBoxModelFilterSet
from .models import CsafDocument, CsafMatch


class CsafDocumentFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafDocument.
    """
    class Meta:
        model = CsafDocument
        fields = ('id', 'title', 'url', 'version', 'lang', 'publisher')

    def search(self, queryset, title, value):
        return queryset.filter(title__icontains=value)


class CsafMatchFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafMatch.
    """
    class Meta:
        model = CsafMatch
        fields = ()

    status = django_filters.MultipleChoiceFilter(
        choices=CsafMatch.Status,
        null_value=None
    )

    def search(self, queryset, status, value):
        return queryset.filter(status__in=value)

