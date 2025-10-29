"""
    This file provides all the table definitions implemented and used by the CSAF-Plugin.
"""
import django_tables2 as tables
from dcim.models import Device
from dcim.tables.devices import DeviceTable
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable
from .models import (CsafDocument, CsafMatch)


class CsafDocumentTable(NetBoxTable):
    """
        Table for the CsafDocument model.
    """
    class Meta(NetBoxTable.Meta):
        model = CsafDocument
        fields = ('id', 'title', 'docurl', 'version', 'lang', 'publisher', 'match_count')
        default_columns = ('id', 'title', 'docurl', 'link', 'version', 'lang', 'publisher')

    title = tables.Column(
        linkify=True,
        verbose_name='Title'
    )
    link = tables.Column(
        accessor='docurl',
        verbose_name='Link')

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}"><i class="mdi mdi-link-variant"></i>', external)

class CsafMatchListForDeviceTable(NetBoxTable):
    """
        Table for the CsafMatches for a single device
    """
    device = tables.Column(
        linkify=True
    )
    software = tables.Column(
        linkify=True
    )
    csaf_document = tables.Column(
        linkify=True
    )
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')
        default_columns = ('id', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')

class CsafMatchListForCsafDocumentTable(NetBoxTable):
    """
        Table for the CsafMatches for a single CsafDocument
    """
    device = tables.Column(
        linkify=True
    )
    software = tables.Column(
        linkify=True
    )
    csaf_document = tables.Column(
        linkify=True
    )
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')
        default_columns = ('id', 'device', 'software', 'score', 'time', 'status', 'description', 'product_name_id')

class CsafMatchListForSoftwareTable(NetBoxTable):
    """
        Table for the CsafMatches for a single Software
    """
    device = tables.Column(
        linkify=True
    )
    software = tables.Column(
        linkify=True
    )
    csaf_document = tables.Column(
        linkify=True
    )
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')
        default_columns = ('id', 'device', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')



class CsafMatchTable(NetBoxTable):
    """
        Table for the CsafMatch model.
    """
    device = tables.Column(
        linkify=True
    )
    software = tables.Column(
        linkify=True
    )
    csaf_document = tables.Column(
        linkify=True
    )
    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')
        default_columns = ('id', 'device', 'software', 'csaf_document', 'score', 'time', 'status', 'description', 'product_name_id')


class DevicesWithMatchTable(DeviceTable):
    """
        Table of Devices with a Match count.
    """
    new_count = tables.Column(
        verbose_name=_('New Matches')
    )
    confirmed_count = tables.Column(
        verbose_name=_('Confirmed Matches')
    )
    resolved_count = tables.Column(
        verbose_name=_('Resolved Matches')
    )
    total_count = tables.Column(
        verbose_name=_('Total Matches')
    )

    class Meta(NetBoxTable.Meta):
        model = Device
        fields = ('pk', 'id', 'name', 'status', 'tenant', 'tenant_group', 'role', 'manufacturer', 'device_type',
            'serial', 'asset_tag', 'region', 'site_group', 'site', 'location', 'rack', 'parent_device',
            'device_bay_position', 'position', 'face', 'latitude', 'longitude', 'airflow', 'primary_ip', 'primary_ip4',
            'primary_ip6', 'oob_ip', 'cluster', 'virtual_chassis', 'vc_position', 'vc_priority', 'description',
            'config_template', 'comments', 'contacts', 'tags', 'created', 'last_updated',
            'new_count', 'confirmed_count', 'resolved_count', 'total_count')
        default_columns = ('id', 'name', 'description', 'status', 'new_count', 'confirmed_count', 'resolved_count', 'total_count')


