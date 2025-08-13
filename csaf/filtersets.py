from netbox.filtersets import NetBoxModelFilterSet
from .models import CsafDocument, CsafMatch
from django.db.models import Q


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
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')

    def search(self, queryset, description, value):
        return queryset.filter(description__icontains=value)

