"""
    These classes are needed for bulk update and delete operations.
"""
from netbox.api.viewsets import NetBoxModelViewSet
from .. import filtersets, models
from .serializers import CsafDocumentSerializer, CsafMatchSerializer

from django.db.models import Count

class CsafDocumentViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafDocument.
    """
    queryset = models.CsafDocument.objects.all()
    serializer_class = CsafDocumentSerializer
    filterset_class = filtersets.CsafDocumentFilterSet


class CsafMatchViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafMatch.
    """
    queryset = models.CsafMatch.objects.all()
    serializer_class = CsafMatchSerializer
    filterset_class = filtersets.CsafMatchFilterSet
