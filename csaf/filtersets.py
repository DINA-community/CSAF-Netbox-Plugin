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
        fields = ('id', 'title', 'docurl', 'version', 'lang', 'publisher')

    def search(self, queryset, title, value):
        if not value.strip():
            return queryset
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
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(description__icontains=value) |
            Q(csaf_document__title__icontains=value) |
            Q(software__name__icontains=value) |
            Q(device__name__icontains=value)
        )

