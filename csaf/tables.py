"""
    This file provides all the table definitions implemented and used by the CSAF-Plugin.
"""

from netbox.tables import NetBoxTable
from .models import (CsafDocument, CsafMatch)


class CsafDocumentTable(NetBoxTable):
    """
        Table for the CsafDocument model.
    """
    class Meta(NetBoxTable.Meta):
        model = CsafDocument
        fields = ('id', 'title', 'url', 'version', 'lang', 'publisher')
        default_columns = ('id', 'title', 'url', 'version', 'lang', 'publisher')

class CsafMatchListForDeviceTable(NetBoxTable):
    """
        Table for the CsafMatches for a single device
    """
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
        default_columns = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
