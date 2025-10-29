from netbox.api.serializers import NetBoxModelSerializer
from ..models import (CsafDocument, CsafMatch)
from drf_spectacular.utils import extend_schema_field
from utilities.api import get_serializer_for_model


class CsafDocumentSerializer(NetBoxModelSerializer):
    """
    REST API Model Serializer for CsafDocument.
    """
    class Meta:
        model = CsafDocument
        fields = ('id', 'title', 'docurl', 'version', 'lang', 'publisher')


class CsafMatchSerializer(NetBoxModelSerializer):
    """
    REST API Model Serializer for CsafMatch.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')

