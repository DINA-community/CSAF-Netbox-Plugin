"""
    This file provides all the table definitions implemented and used by the CSAF-Plugin.
"""
import django_tables2 as tables
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

    title = tables.Column(
        linkify=True,
        verbose_name='Title'
    )

class CsafMatchListForDeviceTable(NetBoxTable):
    """
        Table for the CsafMatches for a single device
    """
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
        default_columns = ('id', 'software', 'csaf_document', 'score', 'time', 'status', 'description')

class CsafMatchListForCsafDocumentTable(NetBoxTable):
    """
        Table for the CsafMatches for a single CsafDocument
    """
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
        default_columns = ('id', 'device', 'software', 'score', 'time', 'status', 'description')

class CsafMatchListForSoftwareTable(NetBoxTable):
    """
        Table for the CsafMatches for a single Software
    """
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
        default_columns = ('id', 'device', 'csaf_document', 'score', 'time', 'status', 'description')



class CsafMatchTable(NetBoxTable):
    """
        Table for the CsafMatch model.
    """
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')
        default_columns = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description')


