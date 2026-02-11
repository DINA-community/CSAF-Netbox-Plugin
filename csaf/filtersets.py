import django_filters
from dcim.models.devices import Device
from django import forms
from django_filters import NumberFilter
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from utilities.filters import MultiValueCharFilter
from d3c.models import Software
from .models import CsafDocument, CsafMatch


class CsafDocumentFilterSet(NetBoxModelFilterSet):
    """
    Definition of the Filterset for CsafDocument.
    """
    title = MultiValueCharFilter(
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
        fields = ('id', 'device_id', 'software_id', 'csaf_document_id', 'status')

    device_id = django_filters.ModelMultipleChoiceFilter(
        queryset = Device.objects.all(),
        label = 'Devices',
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

