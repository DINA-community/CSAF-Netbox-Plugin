from netbox.api.serializers import NetBoxModelSerializer
from ..models import (CsafDocument, CsafMatch, CsafVulnerability)
from drf_spectacular.utils import extend_schema_field
from utilities.api import get_serializer_for_model


class CsafDocumentSerializer(NetBoxModelSerializer):
    """
    REST API Model Serializer for CsafDocument.
    """
    brief_fields = ('id', 'display', 'title', 'lang', 'publisher')
    class Meta:
        model = CsafDocument
        fields = ('id', 'display', 'title', 'docurl', 'version', 'lang', 'publisher')


class CsafMatchSerializer(NetBoxModelSerializer):
    """
    REST API Model Serializer for CsafMatch.
    """
    class Meta:
        model = CsafMatch
        fields = ('id', 'device', 'module', 'software', 'csaf_document', 'score', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')


class CsafVulnerabilitySerializer(NetBoxModelSerializer):
    """
    REST API Model Serializer for CsafVulnerability.
    """
    class Meta:
        model = CsafVulnerability
        fields = ('id', 'csaf_document', 'ordinal', 'vulnerability_id', 'cve', 'title', 'summary', 'cwe', 'cvss_base_score', 'product_ids')
