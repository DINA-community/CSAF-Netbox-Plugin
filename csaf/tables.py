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
