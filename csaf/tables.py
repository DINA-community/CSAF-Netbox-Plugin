"""
    This file provides all the table definitions implemented and used by the CSAF-Plugin.
"""
import django_tables2 as tables
from dcim.models import Device, Module
from dcim.tables.devices import DeviceTable
from dcim.tables.modules import ModuleTable
from django.shortcuts import render
from django.middleware.csrf import get_token
from django.utils.html import format_html, format_html_join
from django.utils.translation import gettext_lazy as _
from netbox.tables import NetBoxTable, columns
from .models import (CsafDocument, CsafMatch, CsafVulnerability)
from d3c.models import Software
from d3c.tables import SoftwareTable


def render_vulnerability_links(record):
    vulns = list(record.related_vulnerabilities)
    if not vulns:
        return '-'

    rendered = format_html_join(
        ', ',
        '<a href="{}">{}</a>',
        ((vuln.get_absolute_url(), vuln.vulnerability_id) for vuln in vulns[:5]),
    )
    if len(vulns) <= 5:
        return rendered
    return format_html('{} (+{})', rendered, len(vulns) - 5)


def get_match_asset(record):
    if record.device is not None:
        return record.device
    if record.module is not None:
        return record.module
    if record.software is not None:
        return record.software
    return None


def get_match_asset_type(record):
    if record.device is not None:
        return 'Device'
    if record.module is not None:
        return 'Module'
    if record.software is not None:
        return 'Software'
    return '-'


def render_remediation_status_with_progress(record):
    progress = record.remediation_progress
    status_label = record.get_remediation_status_display()
    return format_html(
        '<div>{}</div>'
        '<div class="progress mt-1" style="height: 0.5rem;">'
        '<div class="progress-bar bg-success" role="progressbar" style="width: {}%;" '
        'aria-valuenow="{}" aria-valuemin="0" aria-valuemax="100"></div>'
        '<div class="progress-bar bg-warning" role="progressbar" style="width: {}%;" '
        'aria-valuenow="{}" aria-valuemin="0" aria-valuemax="100"></div>'
        '</div>'
        '<small class="text-muted">{}/{} resolved, {} in progress</small>',
        status_label,
        progress['resolved_percentage'],
        progress['resolved_percentage'],
        progress['in_progress_percentage'],
        progress['in_progress_percentage'],
        progress['resolved'],
        progress['total'],
        progress['in_progress'],
    )

def render_acceptance_status_dropdown(record, request):
    if request is None or not request.user.has_perm('csaf.edit_csafmatch'):
        return record.get_acceptance_status_display()

    csrf_token = get_token(request)
    action = request.get_full_path()
    current_label = record.get_acceptance_status_display()
    menu_items = []
    for status in record.AcceptanceStatus:
        is_active = status.value == record.acceptance_status
        item_class = 'dropdown-item active' if is_active else 'dropdown-item'
        menu_items.append((
            action,
            csrf_token,
            record.pk,
            item_class,
            status.value,
            status.label,
        ))

    return format_html(
        '<div class="dropdown">'
        '<button type="button" class="btn btn-sm btn-outline-primary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">{}</button>'
        '<ul class="dropdown-menu">{}</ul>'
        '</div>',
        current_label,
        format_html_join(
            '',
            '<li>'
            '<form method="post" action="{}" class="d-inline">'
            '<input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<input type="hidden" name="pk" value="{}">'
            '<button type="submit" class="{}" name="targetAccStatus" value="{}">{}</button>'
            '</form>'
            '</li>',
            menu_items,
        ),
    )


class CsafDocumentTable(NetBoxTable):
    """
        Table for the CsafDocument model.
    """
    class Meta(NetBoxTable.Meta):
        model = CsafDocument
        fields = ('id', 'title', 'tracking_id', 'docurl', 'version', 'lang', 'publisher',
                  'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')
        default_columns = ('id', 'title', 'tracking_id', 'docurl', 'link', 'version', 'lang', 'publisher',
                           'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')

    title = tables.Column(
        linkify=True,
        verbose_name='Title'
    )
    link = tables.Column(
        accessor='docurl',
        verbose_name='Link')
    new_count = tables.Column(
        verbose_name=_('New Matches')
    )
    confirmed_count = tables.Column(
        verbose_name=_('Confirmed Matches')
    )
    reopened_count = tables.Column(
        verbose_name=_('Reopened Matches')
    )
    resolved_count = tables.Column(
        verbose_name=_('Resolved Matches')
    )
    total_count = tables.Column(
        verbose_name=_('Total Matches')
    )

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}" target="_blank"><i class="mdi mdi-link-variant"></i>', external)


class CsafMatchListForDeviceTable(NetBoxTable):
    """
        Table for the CsafMatches for a single device
    """
    asset = tables.Column(
        empty_values=(),
        verbose_name='Asset',
        orderable=False,
    )
    type = tables.Column(
        empty_values=(),
        verbose_name='Type',
        orderable=False,
    )
    csaf_document = tables.Column(
        linkify=True
    )
    tracking_id = tables.Column(
        accessor='csaf_document.tracking_id',
        verbose_name='Tracking ID',
    )
    link = tables.Column(
        accessor='csaf_document.docurl',
        verbose_name='Link')
    score = tables.TemplateColumn(
        template_code='{{ value|floatformat:0 }}'
    )
    vulnerabilities = tables.Column(
        empty_values=(),
        verbose_name='Vulnerabilities',
        orderable=False,
    )
    actions = columns.ActionsColumn(
        extra_buttons='' \
            '{% if record.acceptance_status not in "NO" %}<button type="submit" name="renew" value="{{ record.id }}" class="btn btn-yellow"><i class="mdi mdi-arrow-left-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "C" %}<button type="submit" name="accept" value="{{ record.id }}" class="btn btn-green"><i class="mdi mdi-arrow-right-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "F" %}<button type="submit" name="reject" value="{{ record.id }}" class="btn btn-red"><i class="mdi mdi-close-thick"></i></button>{% endif %}')

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}" target="_blank"><i class="mdi mdi-link-variant"></i></a>', external)

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')
        default_columns = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')

    def render_vulnerabilities(self, record):
        return render_vulnerability_links(record)

    def render_asset(self, record):
        asset = get_match_asset(record)
        if asset is None:
            return '-'
        return format_html('<a href="{}">{}</a>', asset.get_absolute_url(), asset)

    def render_type(self, record):
        return get_match_asset_type(record)

    def render_remediation_status(self, record):
        return render_remediation_status_with_progress(record)

    def render_acceptance_status(self, record):
        return render_acceptance_status_dropdown(record, getattr(self, 'request', None))


class CsafMatchListForModuleTable(NetBoxTable):
    """
        Table for the CsafMatches for a single Module
    """
    asset = tables.Column(
        empty_values=(),
        verbose_name='Asset',
        orderable=False,
    )
    type = tables.Column(
        empty_values=(),
        verbose_name='Type',
        orderable=False,
    )
    csaf_document = tables.Column(
        linkify=True
    )
    tracking_id = tables.Column(
        accessor='csaf_document.tracking_id',
        verbose_name='Tracking ID',
    )
    link = tables.Column(
        accessor='csaf_document.docurl',
        verbose_name='Link')
    score = tables.TemplateColumn(
        template_code='{{ value|floatformat:0 }}'
    )
    actions = columns.ActionsColumn(
        extra_buttons='' \
            '{% if record.acceptance_status not in "NO" %}<button type="submit" name="renew" value="{{ record.id }}" class="btn btn-yellow"><i class="mdi mdi-arrow-left-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "C" %}<button type="submit" name="accept" value="{{ record.id }}" class="btn btn-green"><i class="mdi mdi-arrow-right-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "F" %}<button type="submit" name="reject" value="{{ record.id }}" class="btn btn-red"><i class="mdi mdi-close-thick"></i></button>{% endif %}')

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}" target="_blank"><i class="mdi mdi-link-variant"></i></a>', external)

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')
        default_columns = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')

    def render_asset(self, record):
        asset = get_match_asset(record)
        if asset is None:
            return '-'
        return format_html('<a href="{}">{}</a>', asset.get_absolute_url(), asset)

    def render_type(self, record):
        return get_match_asset_type(record)

    def render_remediation_status(self, record):
        return render_remediation_status_with_progress(record)

    def render_acceptance_status(self, record):
        return render_acceptance_status_dropdown(record, getattr(self, 'request', None))


class CsafMatchListForCsafDocumentTable(NetBoxTable):
    """
        Table for the CsafMatches for a single CsafDocument
    """
    asset = tables.Column(
        empty_values=(),
        verbose_name='Asset',
        orderable=False,
    )
    type = tables.Column(
        empty_values=(),
        verbose_name='Type',
        orderable=False,
    )
    csaf_document = tables.Column(
        linkify=True
    )
    tracking_id = tables.Column(
        accessor='csaf_document.tracking_id',
        verbose_name='Tracking ID',
    )
    score = tables.TemplateColumn(
        template_code='{{ value|floatformat:0 }}'
    )
    vulnerabilities = tables.Column(
        empty_values=(),
        verbose_name='Vulnerabilities',
        orderable=False,
    )
    actions = columns.ActionsColumn(
        extra_buttons='' \
            '{% if record.acceptance_status not in "NO" %}<button type="submit" name="renew" value="{{ record.id }}" class="btn btn-yellow"><i class="mdi mdi-arrow-left-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "C" %}<button type="submit" name="accept" value="{{ record.id }}" class="btn btn-green"><i class="mdi mdi-arrow-right-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "F" %}<button type="submit" name="reject" value="{{ record.id }}" class="btn btn-red"><i class="mdi mdi-close-thick"></i></button>{% endif %}')

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')
        default_columns = ('id', 'asset', 'type', 'tracking_id', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')

    def render_vulnerabilities(self, record):
        return render_vulnerability_links(record)

    def render_asset(self, record):
        asset = get_match_asset(record)
        if asset is None:
            return '-'
        return format_html('<a href="{}">{}</a>', asset.get_absolute_url(), asset)

    def render_type(self, record):
        return get_match_asset_type(record)

    def render_remediation_status(self, record):
        return render_remediation_status_with_progress(record)

    def render_acceptance_status(self, record):
        return render_acceptance_status_dropdown(record, getattr(self, 'request', None))


class CsafMatchListForSoftwareTable(NetBoxTable):
    """
        Table for the CsafMatches for a single Software
    """
    asset = tables.Column(
        empty_values=(),
        verbose_name='Asset',
        orderable=False,
    )
    type = tables.Column(
        empty_values=(),
        verbose_name='Type',
        orderable=False,
    )
    csaf_document = tables.Column(
        linkify=True
    )
    tracking_id = tables.Column(
        accessor='csaf_document.tracking_id',
        verbose_name='Tracking ID',
    )
    link = tables.Column(
        accessor='csaf_document.docurl',
        verbose_name='Link')
    score = tables.TemplateColumn(
        template_code='{{ value|floatformat:0 }}'
    )
    vulnerabilities = tables.Column(
        empty_values=(),
        verbose_name='Vulnerabilities',
        orderable=False,
    )
    actions = columns.ActionsColumn(
        extra_buttons='' \
            '{% if record.acceptance_status not in "NO" %}<button type="submit" name="renew" value="{{ record.id }}" class="btn btn-yellow"><i class="mdi mdi-arrow-left-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "C" %}<button type="submit" name="accept" value="{{ record.id }}" class="btn btn-green"><i class="mdi mdi-arrow-right-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "F" %}<button type="submit" name="reject" value="{{ record.id }}" class="btn btn-red"><i class="mdi mdi-close-thick"></i></button>{% endif %}')

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}" target="_blank"><i class="mdi mdi-link-variant"></i></a>', external)

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')
        default_columns = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')

    def render_vulnerabilities(self, record):
        return render_vulnerability_links(record)

    def render_asset(self, record):
        asset = get_match_asset(record)
        if asset is None:
            return '-'
        return format_html('<a href="{}">{}</a>', asset.get_absolute_url(), asset)

    def render_type(self, record):
        return get_match_asset_type(record)

    def render_remediation_status(self, record):
        return render_remediation_status_with_progress(record)

    def render_acceptance_status(self, record):
        return render_acceptance_status_dropdown(record, getattr(self, 'request', None))


class CsafMatchTable(NetBoxTable):
    """
        Table for the CsafMatch model.
    """
    asset = tables.Column(
        empty_values=(),
        verbose_name='Asset',
        orderable=False,
    )
    type = tables.Column(
        empty_values=(),
        verbose_name='Type',
        orderable=False,
    )
    csaf_document = tables.Column(
        linkify=True
    )
    tracking_id = tables.Column(
        accessor='csaf_document.tracking_id',
        verbose_name='Tracking ID',
    )
    link = tables.Column(
        accessor='csaf_document.docurl',
        verbose_name='Link')
    score = tables.TemplateColumn(
        template_code='{{ value|floatformat:0 }}'
    )
    vulnerabilities = tables.Column(
        empty_values=(),
        verbose_name='Vulnerabilities',
        orderable=False,
    )
    actions = columns.ActionsColumn(
        extra_buttons='' \
            '{% if record.acceptance_status not in "NO" %}<button type="submit" name="renew" value="{{ record.id }}" class="btn btn-yellow"><i class="mdi mdi-arrow-left-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "C" %}<button type="submit" name="accept" value="{{ record.id }}" class="btn btn-green"><i class="mdi mdi-arrow-right-thick"></i></button>{% endif %}' \
            '{% if record.acceptance_status != "F" %}<button type="submit" name="reject" value="{{ record.id }}" class="btn btn-red"><i class="mdi mdi-close-thick"></i></button>{% endif %}')

    def render_link(self, value):
        external = value.replace("/api/documents/","/#/documents/")
        return format_html('<a href="{}" target="_blank"><i class="mdi mdi-link-variant"></i></a>', external)

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')
        default_columns = ('id', 'asset', 'type', 'csaf_document', 'tracking_id', 'link', 'score', 'vulnerabilities', 'time', 'acceptance_status', 'remediation_status', 'description', 'product_name_id')

    def render_vulnerabilities(self, record):
        return render_vulnerability_links(record)

    def render_asset(self, record):
        asset = get_match_asset(record)
        if asset is None:
            return '-'
        return format_html('<a href="{}">{}</a>', asset.get_absolute_url(), asset)

    def render_type(self, record):
        return get_match_asset_type(record)

    def render_remediation_status(self, record):
        return render_remediation_status_with_progress(record)

    def render_acceptance_status(self, record):
        return render_acceptance_status_dropdown(record, getattr(self, 'request', None))


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
    reopened_count = tables.Column(
        verbose_name=_('Reopened Matches')
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
            'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')
        default_columns = ('id', 'name', 'description', 'status', 'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')


class ModulesWithMatchTable(ModuleTable):
    """
        Table of Modules with a Match count.
    """
    new_count = tables.Column(
        verbose_name=_('New Matches')
    )
    confirmed_count = tables.Column(
        verbose_name=_('Confirmed Matches')
    )
    reopened_count = tables.Column(
        verbose_name=_('Reopened Matches')
    )
    resolved_count = tables.Column(
        verbose_name=_('Resolved Matches')
    )
    total_count = tables.Column(
        verbose_name=_('Total Matches')
    )

    class Meta(NetBoxTable.Meta):
        model = Module
        fields = ('pk', 'id', 'device', 'module_bay', 'manufacturer', 'module_type', 'status', 'serial', 'asset_tag',
            'description', 'comments', 'tags', 'created', 'last_updated',
            'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')
        default_columns = ('id', 'device', 'module_bay', 'manufacturer', 'module_type', 'status', 'serial', 'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')


class SynchroniserTable(NetBoxTable):
    class Meta(NetBoxTable.Meta):
        fields = ('name', 'last_run', 'actions')
        fields = fields


class SoftwareWithMatchTable(SoftwareTable):
    """
        Table of Software with a Match count.
    """
    new_count = tables.Column(
        verbose_name=_('New Matches')
    )
    confirmed_count = tables.Column(
        verbose_name=_('Confirmed Matches')
    )
    reopened_count = tables.Column(
        verbose_name=_('Reopened Matches')
    )
    resolved_count = tables.Column(
        verbose_name=_('Resolved Matches')
    )
    total_count = tables.Column(
        verbose_name=_('Total Matches')
    )

    class Meta(NetBoxTable.Meta):
        model = Software
        fields = ('id', 'name', 'manufacturer', 'is_firmware', 'version', 'cpe',  'purl',
                  'sbom_url_count', 'hashes_count', 'xgenericuri_count', 'parent_rel_count', 'target_rel_count',
                  'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')
        default_columns = ('id', 'name', 'manufacturer', 'is_firmware', 'version', 'new_count', 'confirmed_count', 'reopened_count', 'resolved_count', 'total_count')


class CsafVulnerabilityTable(NetBoxTable):
    """
        Table for the CsafVulnerability model.
    """
    csaf_document = tables.Column(
        linkify=True
    )
    cvss_base_score = tables.Column(
        empty_values=(),
        verbose_name='CVSS Base Score',
    )

    class Meta(NetBoxTable.Meta):
        model = CsafVulnerability
        fields = ('id', 'csaf_document', 'vulnerability_id', 'cve', 'title', 'cwe', 'cvss_base_score')
        default_columns = ('id', 'csaf_document', 'vulnerability_id', 'cve', 'title', 'cwe', 'cvss_base_score')

    def render_cvss_base_score(self, record):
        return record.cvss_badge


class CsafAssetVulnerabilityTable(NetBoxTable):
    """
        Table showing vulnerabilities for an asset with their related CSAF match.
    """
    vulnerability = tables.Column(
        empty_values=(),
        verbose_name='Vulnerability',
        orderable=False,
    )
    cve = tables.Column(
        empty_values=(),
        verbose_name='CVE',
        orderable=False,
    )
    title = tables.Column(
        empty_values=(),
        verbose_name='Title',
        orderable=False,
    )
    cvss_base_score = tables.Column(
        empty_values=(),
        verbose_name='CVSS Base Score',
        orderable=False,
    )
    match = tables.Column(
        empty_values=(),
        verbose_name='Match',
        orderable=False,
    )
    match_acceptance = tables.Column(
        empty_values=(),
        verbose_name='Match Acceptance',
        orderable=False,
    )
    product_name_id = tables.Column(
        empty_values=(),
        verbose_name='Product ID',
        orderable=False,
    )
    remediation_status = tables.Column(
        empty_values=(),
        verbose_name='Remediation',
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = CsafMatch
        fields = (
            'vulnerability',
            'cve',
            'title',
            'cvss_base_score',
            'match',
            'match_acceptance',
            'product_name_id',
            'remediation_status',
        )
        default_columns = fields

    def render_vulnerability(self, record):
        vulnerability = record.get('vulnerability')
        if vulnerability is None:
            return '-'
        return format_html('<a href="{}">{}</a>', vulnerability.get_absolute_url(), vulnerability.vulnerability_id)

    def render_cve(self, record):
        vulnerability = record.get('vulnerability')
        if vulnerability is None:
            return '-'
        return vulnerability.cve or '-'

    def render_title(self, record):
        vulnerability = record.get('vulnerability')
        if vulnerability is None:
            return '-'
        return vulnerability.title or '-'

    def render_cvss_base_score(self, record):
        vulnerability = record.get('vulnerability')
        if vulnerability is None:
            return '-'
        return vulnerability.cvss_badge

    def render_match(self, record):
        match = record.get('match')
        if match is None:
            return '-'
        return format_html('<a href="{}">#{}</a>', match.get_absolute_url(), match.pk)

    def render_match_acceptance(self, record):
        match = record.get('match')
        if match is None:
            return '-'
        return match.get_acceptance_status_display()

    def render_product_name_id(self, record):
        match = record.get('match')
        if match is None:
            return '-'
        return match.product_name_id or '-'

    def render_remediation_status(self, record):
        match = record.get('match')
        vulnerability = record.get('vulnerability')
        if match is None or vulnerability is None:
            return '-'

        status_value = record.get('status_value', CsafMatch.RemediationStatus.NEW)
        status_label = CsafMatch.RemediationStatus(status_value).label
        request = getattr(self, 'request', None)
        if request is None or not request.user.has_perm('csaf.edit_csafmatch'):
            return status_label

        menu_items = []
        for status in CsafMatch.RemediationStatus:
            item_class = 'dropdown-item active' if status.value == status_value else 'dropdown-item'
            payload = f'{match.pk}:{vulnerability.pk}:{status.value}'
            menu_items.append((item_class, payload, status.label))

        return format_html(
            '<div class="dropdown">'
            '<button type="button" class="btn btn-sm btn-outline-primary dropdown-toggle" data-bs-toggle="dropdown" aria-expanded="false">{}</button>'
            '<ul class="dropdown-menu">{}</ul>'
            '</div>',
            status_label,
            format_html_join(
                '',
                '<li><button type="submit" class="{}" name="vuln_update" value="{}">{}</button></li>',
                menu_items,
            ),
        )
