from datetime import datetime
import json
import logging
from django.conf import settings
from django.core.exceptions import FieldDoesNotExist
import requests
import time
from csaf.api.views import getFromJson, getToken, createDocumentForData
from dcim.models import Device, DeviceType, Module, Manufacturer
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View
from netbox.views import generic
from utilities.exceptions import PermissionsViolation
from utilities.htmx import htmx_partial
from utilities.tables import get_table_configs
from utilities.views import ViewTab, register_model_view, GetReturnURLMixin
from . import forms, models, tables, filtersets
from d3c.models import Software

OK_LABEL = 'OK'

CLEAR_TABLE = {
    'all': {'title':'All'}, 
    'matches': {'title':'Matches'},
    'assets': {'title':'Assets'},
    'csaf': {'title':'CSAF Docs'}
}

RIGHT_SYNC_VIEW = "csaf.viewSynchronisers_csafmatch"
RIGHT_SYNC_START = "csaf.startSynchronisers_csafmatch"
RIGHT_SYNC_STOP = "csaf.stopSynchronisers_csafmatch"
RIGHT_SYNC_CLEAR = "csaf.clearSynchronisers_csafmatch"
RIGHT_CONFIG_VIEW = "csaf.ViewConfig"
RIGHT_DASHBOARD_VIEW = "csaf.view_csafmatch"

COMPONENT_LABELS = {
    'assetsync': 'Asset Sync',
    'csafsync': 'CSAF Sync',
    'matcher': 'Matcher',
    'sync': 'Synchronizer',
}

MATCHER_WEIGHT_FIELD_GROUPS = [
    {
        'title': 'database.freetext_fields',
        'path': ['database', 'freetext_fields'],
        'fields': [
            {'name': 'name', 'default': 0.20},
            {'name': 'hardware_name', 'default': 0.17},
            {'name': 'manufacturer_name', 'default': 0.08},
            {'name': 'device_family', 'default': 0.01},
        ],
    },
    {
        'title': 'database.freetext_fields_weights',
        'path': ['database', 'freetext_fields_weights'],
        'fields': [
            {'name': 'token', 'default': 0.5},
            {'name': 'ngram', 'default': 0.3},
            {'name': 'overlap', 'default': 0.2},
        ],
    },
    {
        'title': 'database.ordered_fields',
        'path': ['database', 'ordered_fields'],
        'fields': [
            {'name': 'version', 'default': 0.10},
            {'name': 'model', 'default': 0.03},
            {'name': 'model_numbers', 'default': 0.03},
            {'name': 'part_numbers', 'default': 0.03},
            {'name': 'serial_numbers', 'default': 0.03},
        ],
    },
    {
        'title': 'database.other_fields',
        'path': ['database', 'other_fields'],
        'fields': [
            {'name': 'cpe', 'default': 0.15},
            {'name': 'purl', 'default': 0.13},
            {'name': 'product_type', 'default': 0.02},
            {'name': 'sbom_urls', 'default': 0.01},
        ],
    },
    {
        'title': 'version.weights',
        'path': ['version', 'weights'],
        'fields': [
            {'name': 'raw', 'default': 0.0},
            {'name': 'package', 'default': 0.15},
            {'name': 'release_prefix', 'default': 0.03},
            {'name': 'release_number', 'default': 0.25},
            {'name': 'release_branch', 'default': 0.05},
            {'name': 'build_number', 'default': 0.04},
            {'name': 'qualifier', 'default': 0.03},
            {'name': 'architecture', 'default': 0.05},
            {'name': 'date', 'default': 0.02},
            {'name': 'epoch', 'default': 0.03},
            {'name': 'min_max_version', 'default': 0.35},
        ],
    },
    {
        'title': 'cpe.weights',
        'path': ['cpe', 'weights'],
        'fields': [
            {'name': 'raw', 'default': 0.01},
            {'name': 'part', 'default': 0.05},
            {'name': 'vendor', 'default': 0.15},
            {'name': 'product', 'default': 0.35},
            {'name': 'version', 'default': 0.30},
            {'name': 'update', 'default': 0.05},
            {'name': 'edition', 'default': 0.02},
            {'name': 'language', 'default': 0.00},
            {'name': 'sw_edition', 'default': 0.02},
            {'name': 'target_sw', 'default': 0.02},
            {'name': 'target_hw', 'default': 0.02},
            {'name': 'other', 'default': 0.01},
        ],
    },
    {
        'title': 'purl.weights',
        'path': ['purl', 'weights'],
        'fields': [
            {'name': 'raw', 'default': 0.02},
            {'name': 'type', 'default': 0.15},
            {'name': 'namespace', 'default': 0.10},
            {'name': 'name', 'default': 0.35},
            {'name': 'version', 'default': 0.30},
            {'name': 'qualifiers', 'default': 0.05},
            {'name': 'subpath', 'default': 0.03},
        ],
    },
    {
        'title': 'ngram.weights',
        'path': ['ngram', 'weights'],
        'fields': [
            {'name': '1', 'default': 0.2},
            {'name': '2', 'default': 0.3},
            {'name': '3', 'default': 0.5},
        ],
    },
]


def normalize_component_name(value):
    if value is None:
        return None
    key = str(value).strip().lower().replace('-', '').replace('_', '').replace(' ', '')
    mapping = {
        'assetsync': 'assetsync',
        'assetsyncer': 'assetsync',
        'assetsynchronizer': 'assetsync',
        'netboxsync': 'assetsync',
        'csafsync': 'csafsync',
        'csafsynchronizer': 'csafsync',
        'isdubasync': 'csafsync',
        'matcher': 'matcher',
        'csafmatcher': 'matcher',
    }
    return mapping.get(key)


def infer_component_type(system, is_matcher=False):
    explicit = normalize_component_name(getFromJson(system, ('component',), None))
    if explicit:
        return explicit
    explicit = normalize_component_name(getFromJson(system, ('type',), None))
    if explicit:
        return explicit
    if is_matcher:
        return 'matcher'

    name = str(getFromJson(system, ('name',), '')).lower()
    if 'matcher' in name:
        return 'matcher'
    if 'netbox' in name or 'asset' in name:
        return 'assetsync'
    if 'isduba' in name or 'csaf' in name:
        return 'csafsync'
    return 'sync'


def status_badge_class(state):
    state = (state or '').lower()
    if state == 'running':
        return 'success'
    if state in ('stop_requested', 'stopping'):
        return 'warning'
    if state in ('failed', 'error'):
        return 'danger'
    if state in ('offline',):
        return 'danger'
    return 'secondary'


def build_metric_cards_for_status(status, component):
    if component == 'matcher':
        return [
            {'label': 'Total Runs', 'value': status.get('total_match_runs', 0), 'kind': 'secondary'},
            {'label': 'Pairs Processed', 'value': status.get('total_pairs_processed', 0), 'kind': 'secondary'},
            {'label': 'Matches Found', 'value': status.get('total_matches_found', 0), 'kind': 'success'},
            {'label': 'Pending Tasks', 'value': status.get('pending_tasks', 0), 'kind': 'warning'},
            {'label': 'Pending Batches', 'value': status.get('pending_match_batches', 0), 'kind': 'warning'},
        ]
    return [
        {'label': 'Products Fetched', 'value': status.get('total_products_fetched', 0), 'kind': 'secondary'},
        {'label': 'Relationships Fetched', 'value': status.get('total_relationships_fetched', 0), 'kind': 'secondary'},
        {'label': 'Pending Products', 'value': status.get('pending_products', 0), 'kind': 'warning'},
        {'label': 'Preprocessed Products', 'value': status.get('preprocessed_products', 0), 'kind': 'info'},
        {'label': 'Pending Relationships', 'value': status.get('pending_relationships', 0), 'kind': 'warning'},
        {'label': 'Data Sources', 'value': status.get('data_sources', 0), 'kind': 'info'},
    ]


class Configuration(View):
    """
    Display the status of configured synchronisers.
    """
    def get(self, request):
        if not request.user.has_perm(RIGHT_CONFIG_VIEW):
            raise PermissionsViolation(f'User does not have permission {RIGHT_CONFIG_VIEW}')
        error_help = False
        systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','urls'), [])

        data = []
        system = systems[2]
        (token, msg) = getSyncToken(request, system)
        if msg != OK_LABEL:
            error_help = True
        if token is None:
            return render(request, 'csaf/configuration.html', {
                'data': data,
                'error_help': error_help,
        })
        config = getConfig(request, system, token)
        #if config is None:
            #TODO raise error
        meta = config["parameter_info"]
        result: list[dict[str, any]] = []
    
        for attr, info in meta.items():
            value = get_nested(config, attr)
            required = info.get("required", False)
            # default = info.get("default", None)
    
            result.append(
                {
                    "attribute": attr,
                    "valueType": info["type"],
                    "value": value,
                    "status": required,
                    "description": info["description"],
                }
            )

        return render(request, 'csaf/configuration.html', {
            'data': result,
            'error_help': error_help,
        })


class Dashboard(View):
    """
    CSAF dashboard with key statistics and quick links for engineering workflows.
    """

    def get(self, request):
        if not request.user.has_perm(RIGHT_DASHBOARD_VIEW):
            raise PermissionsViolation(f'User does not have permission {RIGHT_DASHBOARD_VIEW}')

        match_counts = models.CsafMatch.objects.aggregate(
            new_count=Count('id', filter=Q(acceptance_status=models.CsafMatch.AcceptanceStatus.NEW)),
            reopened_count=Count('id', filter=Q(acceptance_status=models.CsafMatch.AcceptanceStatus.REOPENED)),
            confirmed_count=Count('id', filter=Q(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)),
            false_positive_count=Count('id', filter=Q(acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)),
        )
        remediation_counts = models.CsafMatch.objects.filter(
            acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
        ).aggregate(
            open_count=Count(
                'id',
                filter=Q(remediation_status__in=[
                    models.CsafMatch.RemediationStatus.NEW,
                    models.CsafMatch.RemediationStatus.IN_PROGRESS,
                ]),
            ),
            resolved_count=Count(
                'id',
                filter=Q(remediation_status=models.CsafMatch.RemediationStatus.RESOLVED),
            ),
        )

        document_count = models.CsafDocument.objects.count()
        vulnerability_count = models.CsafVulnerability.objects.count()

        systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'synchronisers', 'urls'), [])
        matcher_statuses = []
        for system in systems:
            if not getFromJson(system, ('isMatcher',), False):
                continue
            name = getFromJson(system, ('name',), 'Unnamed Matcher')
            token, _ = getSyncToken(request, system)
            if token is None:
                matcher_statuses.append({
                    'name': name,
                    'state': 'offline',
                    'running_count': 0,
                    'last_run': None,
                    'last_run_label': 'Unavailable',
                })
                continue
            status = getStatus(request, system, token) or {}
            running = status.get('running', [])
            last_run_ts = status.get('last_matching') or status.get('last_synchronization')
            matcher_statuses.append({
                'name': name,
                'state': status.get('state', 'unknown'),
                'running_count': len(running),
                'last_run': datetime.fromtimestamp(last_run_ts) if last_run_ts else None,
                'last_run_label': (
                    'Currently running'
                    if str(status.get('state', '')).lower() == 'running'
                    else (datetime.fromtimestamp(last_run_ts) if last_run_ts else 'Never')
                ),
            })

        links = {
            'potential_matches': reverse('plugins:csaf:csafmatch_list'),
            'confirmed_matches': reverse('plugins:csaf:csafmatch_confirmed'),
            'new_matches': f"{reverse('plugins:csaf:csafmatch_list')}?statusString=1000",
            'reopened_matches': f"{reverse('plugins:csaf:csafmatch_list')}?statusString=0100",
            'open_remediations': (
                f"{reverse('plugins:csaf:csafmatch_confirmed')}"
                f"?remediation_status={models.CsafMatch.RemediationStatus.NEW}"
                f"&remediation_status={models.CsafMatch.RemediationStatus.IN_PROGRESS}"
            ),
            'resolved_remediations': (
                f"{reverse('plugins:csaf:csafmatch_confirmed')}"
                f"?remediation_status={models.CsafMatch.RemediationStatus.RESOLVED}"
            ),
            'false_positives': f"{reverse('plugins:csaf:csafmatch_list')}?statusString=0001",
            'documents': reverse('plugins:csaf:csafdocument_list'),
            'vulnerabilities': reverse('plugins:csaf:csafvulnerability_list'),
            'synchronisers': reverse('plugins:csaf:synchronisers'),
        }

        return render(request, 'csaf/dashboard.html', {
            'match_counts': match_counts,
            'remediation_counts': remediation_counts,
            'document_count': document_count,
            'vulnerability_count': vulnerability_count,
            'matcher_statuses': matcher_statuses,
            'links': links,
        })

def get_nested(config: dict[str, any], dotted: str) -> any:
    """Liest einen Wert aus dem verschachtelten Dict anhand eines Pfads wie 'Assetsync.Api.port'."""
    parts = dotted.split(".")
    cur = config
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur

class Synchronisers(View):
    """
    Display the status of configured synchronisers.
    """
    def get(self, request):
        if not request.user.has_perm(RIGHT_SYNC_VIEW):
            raise PermissionsViolation(f'User does not have permission {RIGHT_SYNC_VIEW}')
        error_help = False
        systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','urls'), [])

        if result := maybeStartSystem(systems, request):
            return result
        if result := maybeStopSystem(systems, request):
            return result
        if result := maybeTriggerMatch(systems, request):
            return result
        if result := maybeClear(systems, request):
            return result

        data = []
        idx = -1;
        for system in systems:
            idx += 1
            name = getFromJson(system, ('name',), 'Unnamed')
            (token, msg) = getSyncToken(request, system)
            if msg != OK_LABEL:
                error_help = True
            if token is None:
                systemData = {
                    'name': name,
                    'lastSync': '-',
                    'state': msg,
                    'started': '-',
                    'index': idx,
                }
                data.append(systemData)
                continue
            status = getStatus(request, system, token)
            if status is None:
                systemData = {
                    'name': name,
                    'lastSync': '-',
                    'state': 'Offline',
                    'started': '-',
                    'index': idx,
                }
                data.append(systemData)
                continue
            lastRunStr = status.get('last_matching')
            lastRunStr = status.get('last_synchronization', lastRunStr)
            runState = status.get('state', 'Unknown')
            runStateNormalized = str(runState).strip().lower()
            startedStr = status.get('start', None)
            if startedStr is None:
                started = '-'
            else:
                started = datetime.fromtimestamp(startedStr)
            if lastRunStr is None:
                lastSync = 'Never or currently running'
            else:
                lastSync = datetime.fromtimestamp(lastRunStr)
            systemData = {
                'name': name,
                'lastSync': lastSync,
                'state': runState,
                'is_stopped': runStateNormalized == 'stopped',
                'is_running': runStateNormalized == 'running',
                'started': started,
                'index': idx,
            }
            isMatcher = getFromJson(system, ('isMatcher',), False)
            component = infer_component_type(system, is_matcher=isMatcher)
            systemData['component'] = component
            systemData['component_label'] = COMPONENT_LABELS.get(component, COMPONENT_LABELS['sync'])
            systemData['state_badge_class'] = status_badge_class(runState)
            systemData['metric_cards'] = build_metric_cards_for_status(status, component)
            if isMatcher:
                systemData['clear'] = CLEAR_TABLE
                systemData['info'] = buildInfoStringMatcher(system, status)
                systemData['matcher_weight_field_groups'] = MATCHER_WEIGHT_FIELD_GROUPS
                running_tasks = status.get('running', [])
                systemData['running'] = running_tasks
                systemData['running_summary'] = {
                    'running': sum(1 for item in running_tasks if item.get('state') == 'running'),
                    'other': sum(1 for item in running_tasks if item.get('state') != 'running'),
                }
                history = getMatcherHistory(request, system, token, limit=1000)
                systemData['history'] = history or []
            elif 'total_products_fetched' in status:
                systemData['info'] = buildInfoStringCsafSync(system, status)
            if request.user.has_perm(RIGHT_SYNC_START):
                systemData['canStart'] = True
            if request.user.has_perm(RIGHT_SYNC_STOP):
                systemData['canStop'] = True
            if request.user.has_perm(RIGHT_SYNC_CLEAR):
                systemData['canClear'] = True
            data.append(systemData)
        component_order = {'assetsync': 0, 'csafsync': 1, 'matcher': 2, 'sync': 3}
        data.sort(key=lambda row: (component_order.get(row.get('component', 'sync'), 99), row.get('name', '')))

        return render(request, 'csaf/synchronisers.html', {
            'data': data,
            'error_help': error_help,
        })

    def post(self, request):
        if not request.user.has_perm(RIGHT_SYNC_VIEW):
            raise PermissionsViolation(f'User does not have permission {RIGHT_SYNC_VIEW}')

        systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'synchronisers', 'urls'), [])
        if result := maybeStartSystem(systems, request):
            return result
        if result := maybeStopSystem(systems, request):
            return result
        if result := maybeTriggerMatch(systems, request):
            return result
        if result := maybeClear(systems, request):
            return result
        return redirect(request.path)


def getRequestValue(request, key, default=None):
    if request.method == 'POST':
        return request.POST.get(key, request.GET.get(key, default))
    return request.GET.get(key, default)


def parseBool(value):
    if value is None:
        return None
    return str(value).strip().lower() in ('1', 'true', 'on', 'yes')


def parseMatcherWeightFields(request):
    matching_config = {}
    for key, raw_value in request.POST.items():
        if not key.startswith('weight__'):
            continue
        value = str(raw_value).strip()
        if value == '':
            continue

        path = key.split('__')[1:]
        if len(path) == 0:
            continue
        try:
            weight = float(value)
        except ValueError:
            raise ValueError(f'Invalid number for {key}: {raw_value}')

        target = matching_config
        for part in path[:-1]:
            if part not in target or not isinstance(target[part], dict):
                target[part] = {}
            target = target[part]
        target[path[-1]] = weight
    return matching_config


def getIsdubaBaseUrl():
    base_url = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba', 'base_url'), None)
    base_url = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba_base_url'), base_url)
    if base_url:
        return base_url.rstrip('/')

    systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'synchronisers', 'urls'), [])
    for system in systems:
        fallback = getFromJson(system, ('isdubaBaseUrl',), None)
        if fallback:
            return fallback.rstrip('/')
    return None


def queryIsdubaDocuments(query_expression):
    base_url = getIsdubaBaseUrl()
    if not base_url:
        return []

    token = getToken()
    if not token:
        return []

    verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba', 'verify_ssl'), True)
    verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba_verify_ssl'), verify_ssl)
    endpoint = f"{base_url}/api/documents"
    response = requests.get(
        endpoint,
        headers={'authorization': 'Bearer ' + token},
        params={
            'query': query_expression,
            'columns': 'id title tracking_id publisher',
            'count': '1',
            'advisories': 'false',
            'aggregate': 'false',
        },
        verify=verify_ssl,
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()

    items = []
    if isinstance(payload, dict):
        raw_items = payload.get('documents') or payload.get('results') or payload.get('items') or payload.get('data') or []
        if isinstance(raw_items, list):
            items = raw_items
    elif isinstance(payload, list):
        items = payload

    result = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        # In some responses documents may be wrapped in aggregated `data` entries.
        candidate = dict(item)
        if isinstance(item.get('data'), list):
            merged = {}
            for row in item.get('data'):
                if isinstance(row, dict):
                    merged.update(row)
            candidate.update(merged)

        doc_id = candidate.get('id', item.get('id'))
        if doc_id is None:
            continue
        docurl = f"{endpoint}/{doc_id}"
        tracking_id = (
            candidate.get('tracking_id')
            or getFromJson(candidate, ('tracking', 'id'), None)
            or getFromJson(candidate, ('document', 'tracking', 'id'), None)
        )

        title = (
            candidate.get('title')
            or tracking_id
            or getFromJson(candidate, ('document', 'title'), None)
            or str(docurl)
        )

        docurl = str(docurl)
        if docurl in seen:
            continue
        seen.add(docurl)
        result.append({
            'docurl': docurl,
            'title': str(title),
            'tracking_id': str(tracking_id) if tracking_id else '',
            'external_url': docurl.replace('/api/documents/', '/#/documents/'),
        })

    return result


def queryIsdubaDocumentsByName(query):
    if not query:
        return []

    escaped_query = query.replace('"', '\\"')
    query_expression = (
        f'$title "{escaped_query}" ilike '
        f'$tracking_id "{escaped_query}" ilike or'
    )
    return queryIsdubaDocuments(query_expression)


def queryIsdubaDocumentsByTrackingId(query):
    if not query:
        return []

    escaped_query = query.replace('"', '\\"')
    query_expression = f'$tracking_id "{escaped_query}" ilike'
    return queryIsdubaDocuments(query_expression)


@register_model_view(models.CsafDocument, name='add_by_name', path='add-by-name', detail=False)
class CsafDocumentAddByNameView(generic.ObjectListView):
    """
    Alternative UI for adding CSAF documents by searching names in ISDuBA.
    """
    queryset = models.CsafDocument.objects.all()
    template_name = 'csaf/csafdocument_add_by_name.html'

    def get(self, request):
        if not request.user.has_perm('csaf.add_csafdocument'):
            raise PermissionsViolation('User does not have permission csaf.add_csafdocument')

        query = (request.GET.get('q') or '').strip()
        results = []
        if query:
            try:
                results = queryIsdubaDocumentsByName(query)
            except requests.exceptions.RequestException as ex:
                messages.error(request, f'Failed to query ISDuBA: {ex}')

        choices = [(entry['docurl'], f"{entry['title']} ({entry['docurl']})") for entry in results]
        form = forms.CsafDocumentSearchForm(initial={'q': query})
        form.fields['selected_docurls'].choices = choices

        return render(request, self.template_name, {
            'form': form,
            'query': query,
            'result_count': len(results),
            'results': results,
        })

    def post(self, request):
        if not request.user.has_perm('csaf.add_csafdocument'):
            raise PermissionsViolation('User does not have permission csaf.add_csafdocument')

        query = (request.POST.get('q') or '').strip()
        try:
            results = queryIsdubaDocumentsByName(query) if query else []
        except requests.exceptions.RequestException as ex:
            messages.error(request, f'Failed to query ISDuBA: {ex}')
            return redirect(request.path + (f'?q={query}' if query else ''))

        valid_docurls = {entry['docurl'] for entry in results}
        selected_docurls = [
            docurl for docurl in request.POST.getlist('selected_docurls')
            if docurl in valid_docurls
        ]
        if not selected_docurls:
            messages.warning(request, 'No documents selected.')
            return redirect(request.path + (f'?q={query}' if query else ''))

        created = 0
        for docurl in selected_docurls:
            createDocumentForData({'docurl': docurl})
            created += 1

        messages.success(request, f'Queued {created} document(s) for import.')
        return redirect('plugins:csaf:csafdocument_list')


@register_model_view(models.CsafDocument, name='add_by_tracking_id', path='add-by-tracking-id', detail=False)
class CsafDocumentAddByTrackingIdView(generic.ObjectListView):
    """
    Alternative UI for adding CSAF documents by searching tracking IDs in ISDuBA.
    """
    queryset = models.CsafDocument.objects.all()
    template_name = 'csaf/csafdocument_add_by_tracking_id.html'

    def get(self, request):
        if not request.user.has_perm('csaf.add_csafdocument'):
            raise PermissionsViolation('User does not have permission csaf.add_csafdocument')

        query = (request.GET.get('q') or '').strip()
        results = []
        if query:
            try:
                results = queryIsdubaDocumentsByTrackingId(query)
            except requests.exceptions.RequestException as ex:
                messages.error(request, f'Failed to query ISDuBA: {ex}')

        choices = [(entry['docurl'], f"{entry['title']} ({entry['docurl']})") for entry in results]
        form = forms.CsafDocumentSearchForm(initial={'q': query})
        form.fields['selected_docurls'].choices = choices

        return render(request, self.template_name, {
            'form': form,
            'query': query,
            'result_count': len(results),
            'results': results,
        })

    def post(self, request):
        if not request.user.has_perm('csaf.add_csafdocument'):
            raise PermissionsViolation('User does not have permission csaf.add_csafdocument')

        query = (request.POST.get('q') or '').strip()
        try:
            results = queryIsdubaDocumentsByTrackingId(query) if query else []
        except requests.exceptions.RequestException as ex:
            messages.error(request, f'Failed to query ISDuBA: {ex}')
            return redirect(request.path + (f'?q={query}' if query else ''))

        valid_docurls = {entry['docurl'] for entry in results}
        selected_docurls = [
            docurl for docurl in request.POST.getlist('selected_docurls')
            if docurl in valid_docurls
        ]
        if not selected_docurls:
            messages.warning(request, 'No documents selected.')
            return redirect(request.path + (f'?q={query}' if query else ''))

        created = 0
        for docurl in selected_docurls:
            createDocumentForData({'docurl': docurl})
            created += 1

        messages.success(request, f'Queued {created} document(s) for import.')
        return redirect('plugins:csaf:csafdocument_list')

def buildInfoStringCsafSync(system, status):
    return {
            'Total products fetched': status.get('total_products_fetched'),
            'Total relationship fetch calls': status.get('total_relationship_fetch_calls'),
            'Total relationships fetched': status.get('total_relationships_fetched'),
            'Pending products': status.get('pending_products'),
            'Pending relationships': status.get('pending_relationships'),
            'Preprocessed products': status.get('preprocessed_products'),
            'Data sources': status.get('data_sources'),
        }

def buildInfoStringMatcher(system, status):
    return {
            'Total Runs': status.get('total_match_runs'),
            'Total Pairs': status.get('total_pairs_processed'),
            'Total Matches': status.get('total_matches_found'),
            'Pending Tasks': status.get('pending_tasks'),
            'Pending Batches': status.get('pending_match_batches')
        }


def maybeTriggerMatch(systems, request):
    trigger = getRequestValue(request, 'trigger', None)
    if (trigger is not None):
        print("Triggering...")
        for system in systems:
            isMatcher = getFromJson(system, ('isMatcher',), False)
            if isMatcher:
                (token, msg) = getSyncToken(request, system)
                if token is not None:
                    triggerMatcher(request, system, token)
                else:
                    print(f"No token: {system}")
        return redirect(request.path)


def triggerMatcher(request, system, token):
    device = getRequestValue(request, 'device', -1)
    module = getRequestValue(request, 'module', -1)
    software = getRequestValue(request, 'software', -1)

    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    startUrl = f"{baseUrl}/task/start"
    try:
        assets = []
        csaf_documents = []
        addUrlForDocument(csaf_documents, getRequestValue(request, 'document', None))
        addUrlForDevice(assets, getRequestValue(request, 'device', None), system)
        addUrlForModule(assets, getRequestValue(request, 'module', None), system)
        addUrlForDeviceType(assets, getRequestValue(request, 'deviceType', None), system)
        addUrlForSoftware(assets, getRequestValue(request, 'software', None), system)
        response = requests.post(
            startUrl,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
            params={
                'assets': assets,
                'csaf_documents': csaf_documents,
            }
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to start {name}: {response.text}")
        else:
            messages.success(request, f"Triggered {name}")
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to trigger {name}: {ex}")


def addUrlForSoftware(list, id, system):
    if id is None:
        return
    try:
        entityId = int(id)
        baseUrl = getFromJson(system, ('netboxBaseUrl',), None)
        if baseUrl is not None:
            devUrl = f'{baseUrl}/api/plugins/d3c/software/{entityId}/'
            list.append(devUrl)
            return

        query = Software.objects.filter(id = entityId)
        try:
            entity = query.get()
            list.append(entity.get_absolute_url())
        except Software.DoesNotExist:
            return
    except ValueError:
        return


def addUrlForDeviceType(list, id, system):
    if id is None:
        return
    try:
        entityId = int(id)
        baseUrl = getFromJson(system, ('netboxBaseUrl',), None)
        query = Device.objects.filter(device_type = entityId)
        try:
            for entity in query:
                if baseUrl is not None:
                    list.append(f'{baseUrl}/api/dcim/devices/{entity.id}/')
                else:
                    list.append(entity.get_absolute_url())
        except Device.DoesNotExist:
            return
    except ValueError:
        return
    

def addUrlForDevice(list, id, system):
    if id is None:
        return
    try:
        entityId = int(id)
        baseUrl = getFromJson(system, ('netboxBaseUrl',), None)
        query = Device.objects.filter(id = entityId)
        try:
            entity = query.get()
            if baseUrl is not None:
                list.append(f'{baseUrl}/api/dcim/devices/{entityId}/')
            else:
                list.append(entity.get_absolute_url())
        except Device.DoesNotExist:
            return
    except ValueError:
        return


def addUrlForModule(list, id, system):
    if id is None:
        return
    try:
        entityId = int(id)
        baseUrl = getFromJson(system, ('netboxBaseUrl',), None)
        query = Module.objects.filter(id = entityId)
        try:
            entity = query.get()
            if baseUrl is not None:
                list.append(f'{baseUrl}/api/dcim/modules/{entityId}/')
            else:
                list.append(entity.get_absolute_url())
        except Module.DoesNotExist:
            return
    except ValueError:
        return


def addUrlForDocument(list, id):
    if id is None:
        return
    try:
        docId = int(id)
        query = models.CsafDocument.objects.filter(id = docId)
        try:
            entity = query.get()
            list.append(entity.docurl)
        except models.CsafDocument.DoesNotExist:
            return
    except ValueError:
        return


def maybeStartSystem(systems, request):
    try:
        startStr = getRequestValue(request, 'start', -1)
        startIdx = int(startStr)
        if startIdx >= 0 and startIdx < len(systems):
            if not request.user.has_perm(RIGHT_SYNC_START):
                messages.error(request, f'User does not have permission {RIGHT_SYNC_START}')
                return

            system = systems[startIdx]
            matchingConfig = None
            forceRecompute = None
            matchingConfigMode = getRequestValue(request, 'matching_config_mode', 'json')
            if matchingConfigMode == 'fields':
                try:
                    matchingConfig = parseMatcherWeightFields(request)
                except ValueError as ex:
                    messages.error(request, str(ex))
                    return redirect(request.path)
                if len(matchingConfig) == 0:
                    matchingConfig = None
            else:
                matchingConfigRaw = getRequestValue(request, 'matching_config', None)
                if matchingConfigRaw is not None and str(matchingConfigRaw).strip() != '':
                    try:
                        matchingConfig = json.loads(matchingConfigRaw)
                    except json.JSONDecodeError as ex:
                        messages.error(request, f'Invalid matcher weight JSON: {ex}')
                        return redirect(request.path)
                    if not isinstance(matchingConfig, dict):
                        messages.error(request, 'Invalid matcher weight JSON: expected JSON object')
                        return redirect(request.path)
            forceRecompute = parseBool(getRequestValue(request, 'force_recompute', None))

            (token, msg) = getSyncToken(request, system)
            if token is not None:
                startSystem(
                    request,
                    system,
                    token,
                    matchingConfig=matchingConfig,
                    forceRecompute=forceRecompute,
                )
            return redirect(request.path)
    except ValueError:
        messages.error(request, f"Not an int: {startStr}")


def startSystem(request, system, token, matchingConfig=None, forceRecompute=None):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    isMatcher = getFromJson(system, ('isMatcher',), False)
    startUrl = f"{baseUrl}/task/start"
    try:
        requestPayload = {}
        if isMatcher and matchingConfig is not None:
            requestPayload['matching_config'] = matchingConfig
        if isMatcher and forceRecompute is not None:
            requestPayload['force_recompute'] = forceRecompute

        requestArgs = {
            'headers': {'Authorization': 'Bearer ' + token},
            'verify': verifySsl,
        }
        if requestPayload:
            requestArgs['json'] = requestPayload

        response = requests.post(
            startUrl,
            **requestArgs,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to start {name}: {response.text}")
        else:
            messages.success(request, f"Started {name}")
            time.sleep(0.2) # Give the system some time before requesting status
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to start {name}: {ex}")


def maybeStopSystem(systems, request):
    try:
        stopStr = getRequestValue(request, 'stop', -1)
        stopIdx = int(stopStr)
        if stopIdx >= 0 and stopIdx < len(systems):
            if not request.user.has_perm(RIGHT_SYNC_STOP):
                messages.error(request, f'User does not have permission {RIGHT_SYNC_STOP}')
                return
            system = systems[stopIdx]
            (token, msg) = getSyncToken(request, system)
            if token is not None:
                stopSystem(request, system, token)
            return redirect(request.path)
    except ValueError:
        messages.error(request, f"Not an int: {stopStr}")


def stopSystem(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    url = f"{baseUrl}/task/stop"
    try:
        taskIdStr = getRequestValue(request, 'task_id', -1)
        taskId = int(taskIdStr)
    except ValueError:
        taskId = -1
    if taskId >= 0:
        url += f'?task_id={taskId}'

    try:
        response = requests.post(
            url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to stop {name}: {response.text}")
        else:
            messages.success(request, f"Stopped {name}")
            time.sleep(0.2) # Give the system some time before requesting status
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to stop {name}: {ex}")


def maybeClear(systems, request):
    try:
        clearStr = getRequestValue(request, 'clear', None)
        if clearStr is None:
            return False
        if not request.user.has_perm(RIGHT_SYNC_CLEAR):
            messages.error(request, f'User does not have permission {RIGHT_SYNC_CLEAR}')
            return
        if not clearStr in CLEAR_TABLE:
            messages.error(request, f"Unknown clear command: {clearStr}")
            return False
        idxStr = getRequestValue(request, 'idx', -1)
        clearIdx = int(idxStr)
        if clearIdx >= 0 and clearIdx < len(systems):
            system = systems[clearIdx]
            (token, msg) = getSyncToken(request, system)
            if token is not None:
                clearSystem(request, system, token, clearStr)
            return redirect(request.path)
    except ValueError:
        messages.error(request, f"Not an int: {idxStr}")
    return False


def clearSystem(request, system, token, clearType):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl',), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    url = f"{baseUrl}/clear/{clearType}"
    if (clearType == 'assets'):
        url += '?origin_uri=' + getFromJson(system, ('netboxBaseUrl',), '')
    if (clearType == 'csaf'):
        url += '?origin_uri=' + getFromJson(system, ('isdubaBaseUrl',), '')

    try:
        response = requests.post(
            url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to clear {clearType}: {response.text}")
        else:
            messages.success(request, f"Cleared {clearType}")
            time.sleep(0.2) # Give the system some time before requesting status
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to clear {clearType}: {ex}")


def getStatus(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    status_url = f"{baseUrl}/task/status"
    try:
        response = requests.get(
            status_url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to fetch status of {name}: {response.text}")
        result = response.json()
        isMatcher = getFromJson(system, ('isMatcher',), False)
        if isMatcher:
            result['running'] = getRunningMatchers(request, system, token)
        return result
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch status of {name}: {ex}")

def getConfig(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    status_url = f"{baseUrl}/config"
    try:
        response = requests.get(
            status_url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to fetch config of {name}: {response.text}")
        result = response.json()
        return result
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch config of {name}: {ex}")


def getRunningMatchers(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None).rstrip('/')

    name = getFromJson(system, ('name',), 'Unnamed')
    status_url = f"{baseUrl}/task/running"
    try:
        response = requests.get(
            status_url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to fetch running tasks of {name}: {response.text}")
        result = response.json()
        for item in result:
            item['start_time'] = datetime.fromtimestamp(item['start_time'])
            aCount = len(item['assets'])
            dCount = len(item['csaf_documents'])
            details = ''
            if aCount != 0:
                details += f' Assets: {aCount}'
            if dCount != 0:
                details += f' Documents: {dCount}'
            item['details'] = details
            progress = item.get('progress')
            if progress is not None:
                item['progress_pct'] = int(max(0, min(100, round(progress * 100))))
        return result
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch running tasks of {name}: {ex}")


def getMatcherHistory(request, system, token, limit=1000):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'synchronisers', 'verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None).rstrip('/')

    name = getFromJson(system, ('name',), 'Unnamed')
    history_url = f"{baseUrl}/task/history"
    try:
        response = requests.get(
            history_url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
            params={'limit': limit},
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to fetch run history of {name}: {response.text}")
            return []

        result = response.json()
        for item in result:
            started = item.get('start_time')
            finished = item.get('finished_at')
            if started is not None:
                item['start_time'] = datetime.fromtimestamp(started)
            if finished is not None:
                item['finished_at'] = datetime.fromtimestamp(finished)

            trigger = str(item.get('trigger', '')).strip().lower()
            if trigger == 'manual':
                item['trigger_label'] = 'Manual'
            elif trigger in ('schedule', 'scheduled', 'automatic', 'auto'):
                item['trigger_label'] = 'Automatic'
            elif trigger != '':
                item['trigger_label'] = trigger.capitalize()
            else:
                item['trigger_label'] = '-'

            aCount = len(item.get('assets', []))
            dCount = len(item.get('csaf_documents', []))
            details = ''
            if aCount != 0:
                details += f' Assets: {aCount}'
            if dCount != 0:
                details += f' Documents: {dCount}'
            item['details'] = details

            progress = item.get('progress')
            if progress is not None:
                item['progress_pct'] = int(max(0, min(100, round(progress * 100))))
        return result
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch run history of {name}: {ex}")
        return []


def getSyncToken(request, subsystem) -> str:
    """Retrieve an access token via Keycloak."""

    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    username = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','username'), None)
    password = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','password'), None)

    baseUrl = getFromJson(subsystem, ('url',), None)
    name = getFromJson(subsystem, ('name',), 'Unnamed')
    verifySsl = getFromJson(subsystem, ('verify_ssl'), verifySsl)
    username = getFromJson(subsystem, ('username',), username)
    password = getFromJson(subsystem, ('password',), password)

    baseUrl = baseUrl.removesuffix('/')
    token_url = f"{baseUrl}/token"
    try:
        response = requests.post(
            token_url,
            data={
                'username': username,
                'password': password,
            },
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to login to {name}: {response.text}")
            return None,'Login Failed'
        return response.json().get('access_token'), OK_LABEL
    except requests.exceptions.ConnectionError as ex:
        messages.error(request, f"Failed to connect to {name} at {baseUrl}: {ex.__context__.__cause__._message}")
        return None,'Connection failed'
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to login to {name}: {ex}")
        return None,'Unknown error'


@register_model_view(models.CsafDocument)
class CsafDocumentView(generic.ObjectView):
    """ This view handles the request for displaying a CsafDocument. """
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafDocumentTable

    def get(self, request, **kwargs):
        instance = self.get_object(**kwargs)
        instance.link = instance.docurl.replace("/api/documents/","/#/documents/")
        return render(request, self.get_template_name(), {
            'object': instance,
            'tab': self.tab,
            **self.get_extra_context(request, instance),
        })

@register_model_view(models.CsafDocument, name='list', path='', detail=False)
class CsafDocumentListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafDocuments as a table. """
    queryset = models.CsafDocument.objects.annotate(
            new_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'csaf_document': OuterRef('pk')})
                    .filter(acceptance_status__in=[
                        models.CsafMatch.AcceptanceStatus.NEW,
                        models.CsafMatch.AcceptanceStatus.REOPENED])
                    .values('csaf_document')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'csaf_document': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
                    .values('csaf_document')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'csaf_document': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)
                    .values('csaf_document')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            total_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'csaf_document': OuterRef('pk')})
                    .values('csaf_document')
                    .annotate(c=Count('*'))
                    .values('c'))
        )
    table = tables.CsafDocumentTable
    template_name = 'csaf/csafdocument_list.html'
    filterset = filtersets.CsafDocumentFilterSet
    filterset_form = forms.CsafDocumentFilterForm
    actions = {
        'add': {'add'},
        'bulk_edit': {'change'},
        'bulk_delete': {'delete'},
    }


@register_model_view(models.CsafDocument, name='add', detail=False)
@register_model_view(models.CsafDocument, name='edit')
class CsafDocumentEditView(generic.ObjectEditView):
    """ This view handles the edit requests for the CsafDocument model. """
    queryset = models.CsafDocument.objects.all()
    form = forms.CsafDocumentForm


@register_model_view(models.CsafDocument, name='delete')
class CsafDocumentDeleteView(generic.ObjectDeleteView):
    """ This view handles the delete requests for the CsafDocument model. """
    queryset = models.CsafDocument.objects.all()


@register_model_view(models.CsafDocument, 'bulk_delete', path='delete', detail=False)
class CsafDocumentBulkDeleteView(generic.BulkDeleteView):
    """ This view handles the buld delete requests for the CsafDocument model. """
    queryset = models.CsafDocument.objects.all()
    filterset = filtersets.CsafDocumentFilterSet
    table = tables.CsafDocumentTable


@register_model_view(models.CsafMatch)
class CsafMatchView(generic.ObjectView):
    """ This view handles the request for displaying a CsafMatch. """
    queryset = models.CsafMatch.objects.select_related(
        'device',
        'module',
        'software',
        'csaf_document',
    ).prefetch_related('csaf_document__vulnerabilities', 'vulnerability_statuses__vulnerability')

    def post(self, request, **kwargs):
        instance = self.get_object(**kwargs)
        user = request.user
        if not user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        target_acceptance_status = request.POST.get('targetAccStatus')
        if target_acceptance_status:
            if target_acceptance_status not in models.CsafMatch.AcceptanceStatus:
                messages.error(request, f"Unknown acceptance status: {target_acceptance_status}")
                return redirect(request.path)

            if instance.acceptance_status != target_acceptance_status:
                instance.acceptance_status = target_acceptance_status
                instance.save(update_fields=['acceptance_status'])
                messages.success(request, "Updated acceptance status.")
            return redirect(request.path)

        vulnerability_id = request.POST.get('vulnerability_id')
        remediation_status = request.POST.get('targetRemStatus')
        if not vulnerability_id or not remediation_status:
            messages.error(request, "Missing remediation status update data.")
            return redirect(request.path)

        if instance.acceptance_status != models.CsafMatch.AcceptanceStatus.CONFIRMED:
            messages.error(request, "Remediation status can only be changed for confirmed matches.")
            return redirect(request.path)

        if remediation_status not in models.CsafMatch.RemediationStatus:
            messages.error(request, f"Unknown remediation status: {remediation_status}")
            return redirect(request.path)

        try:
            vulnerability = models.CsafVulnerability.objects.get(
                pk=vulnerability_id,
                csaf_document=instance.csaf_document,
            )
        except models.CsafVulnerability.DoesNotExist:
            messages.error(request, "Unknown vulnerability.")
            return redirect(request.path)

        try:
            instance.set_vulnerability_remediation(vulnerability, remediation_status)
        except ValueError as ex:
            messages.error(request, str(ex))
            return redirect(request.path)
        messages.success(request, "Updated vulnerability remediation status.")
        return redirect(request.path)


@register_model_view(models.CsafMatch, name='add', detail=False)
@register_model_view(models.CsafMatch, name='edit')
class CsafMatchEditView(generic.ObjectEditView):
    """ This view handles the edit requests for the CsafMatch model. """
    queryset = models.CsafMatch.objects.all()
    form = forms.CsafMatchForm


@register_model_view(models.CsafMatch, name='delete')
class CsafMatchDeleteView(generic.ObjectDeleteView):
    """ This view handles the delete requests for the CsafMatch model. """
    queryset = models.CsafMatch.objects.all()


@register_model_view(models.CsafMatch, 'bulk_delete', path='delete', detail=False)
class CsafMatchBulkDeleteView(generic.BulkDeleteView):
    """ This view handles the buld delete requests for the CsafMatch model. """
    queryset = models.CsafMatch.objects.select_related(
        'device',
        'software',
        'csaf_document',
    ).prefetch_related('csaf_document__vulnerabilities')
    filterset = filtersets.CsafMatchFilterSet
    table = tables.CsafMatchTable


@register_model_view(models.CsafVulnerability)
class CsafVulnerabilityView(generic.ObjectView):
    """ This view handles the request for displaying a CsafVulnerability. """
    queryset = models.CsafVulnerability.objects.all()


@register_model_view(models.CsafVulnerability, name='list', path='', detail=False)
class CsafVulnerabilityListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafVulnerabilities as a table. """
    queryset = models.CsafVulnerability.objects.all()
    table = tables.CsafVulnerabilityTable
    filterset = filtersets.CsafVulnerabilityFilterSet
    filterset_form = forms.CsafVulnerabilityFilterForm
    actions = {
        'add': {'add'},
        'bulk_edit': {'change'},
        'bulk_delete': {'delete'},
    }


@register_model_view(models.CsafVulnerability, name='add', detail=False)
@register_model_view(models.CsafVulnerability, name='edit')
class CsafVulnerabilityEditView(generic.ObjectEditView):
    """ This view handles the edit requests for the CsafVulnerability model. """
    queryset = models.CsafVulnerability.objects.all()
    form = forms.CsafVulnerabilityForm


@register_model_view(models.CsafVulnerability, name='delete')
class CsafVulnerabilityDeleteView(generic.ObjectDeleteView):
    """ This view handles the delete requests for the CsafVulnerability model. """
    queryset = models.CsafVulnerability.objects.all()


@register_model_view(models.CsafVulnerability, 'bulk_delete', path='delete', detail=False)
class CsafVulnerabilityBulkDeleteView(generic.BulkDeleteView):
    """ This view handles the bulk delete requests for the CsafVulnerability model. """
    queryset = models.CsafVulnerability.objects.all()
    filterset = filtersets.CsafVulnerabilityFilterSet
    table = tables.CsafVulnerabilityTable


# CsafMatches view for New/Reopened Matches
@register_model_view(models.CsafMatch, name='list', path='', detail=False)
class CsafMatchListView(generic.ObjectListView, GetReturnURLMixin):
    """ This view handles the request for displaying multiple CsafMatches as a table. """
    model = models.CsafMatch
    queryset = models.CsafMatch.objects.select_related(
        'device',
        'module',
        'software',
        'csaf_document',
    ).prefetch_related('csaf_document__vulnerabilities', 'vulnerability_statuses')
    filterset = filtersets.CsafMatchFilterSet
    filterset_form = forms.CsafMatchFilterForm
    table = tables.CsafMatchTable
    base_template = 'generic/object_list.html'
    template_name = 'csaf/csafmatch_list.html'
    actions = {
        'add': {'add'},
        'bulk_edit': {'change'},
        'bulk_delete': {'delete'},
    }
    status_filter_enabled = True
    include_confirmed_in_status_filter = False
    view_mode = 'non_confirmed'

    def apply_comparison_column_layout(self, table):
        if 'comparison' not in table.columns.names():
            return

        if self.view_mode == 'non_confirmed':
            table.columns.hide('comparison')
            return

        table.columns.show('comparison')
        sequence = [name for name in table.sequence if name != 'comparison']
        if 'actions' in sequence:
            actions_index = sequence.index('actions')
            sequence.insert(actions_index, 'comparison')
        else:
            sequence.append('comparison')
        table.sequence = sequence

    def get_list_queryset(self, request):
        queryset = self.queryset
        statusString = ''
        acceptance_status = {}

        if self.filterset:
            queryset = self.filterset(request.GET, queryset, request=request).qs

        if self.status_filter_enabled:
            default_status = '1110' if self.include_confirmed_in_status_filter else '1101'
            statusString, acceptance_status, statusSearch = handleStatus(request, deflt=default_status)
            if not self.include_confirmed_in_status_filter:
                statusSearch.discard(models.CsafMatch.AcceptanceStatus.CONFIRMED)
                acceptance_status[str(models.CsafMatch.AcceptanceStatus.CONFIRMED)] = 0
                statusString = ''.join(str(acceptance_status[str(entry)]) for entry in models.CsafMatch.AcceptanceStatus)
            queryset = queryset.filter(acceptance_status__in=statusSearch)
        else:
            queryset = queryset.filter(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)

        return queryset, statusString, acceptance_status

    def get_match_tabs(self):
        return [
            {
                'label': 'Potential CSAF Matches',
                'url': 'plugins:csaf:csafmatch_list',
                'active': self.view_mode == 'non_confirmed',
            },
            {
                'label': 'CSAF Matches',
                'url': 'plugins:csaf:csafmatch_confirmed',
                'active': self.view_mode == 'confirmed',
            },
        ]

    def get(self, request, *args, **kwargs):
        childObjects, statusString, acceptance_status = self.get_list_queryset(request)

        # Determine the available actions
        actions = self.get_permitted_actions(request.user, model=self.model)
        has_bulk_actions = any([a.startswith('bulk_') for a in actions])

        table = self.get_table(childObjects, request, has_bulk_actions)
        self.apply_comparison_column_layout(table)

        # If this is an HTMX request, return only the rendered table HTML
        if htmx_partial(request):
            return render(request, 'htmx/table.html', {
                'table': table,
                'model': self.model,
            })

        return_url = cleanUrl(request.get_full_path())
        return render(request, self.template_name, {
            'model': self.model,
            'base_template': self.base_template,
            'table': table,
            'table_config': f'{table.name}_config',
            'table_configs': get_table_configs(table, request.user),
            'actions': actions,
            'acceptance_status': acceptance_status,
            'statusString': statusString,
            'enums': {'acceptance': models.CsafMatch.AcceptanceStatus, 'remediation': models.CsafMatch.RemediationStatus},
            'statusFilter': self.status_filter_enabled,
            'statusFilterIncludeConfirmed': self.include_confirmed_in_status_filter,
            'match_tabs': self.get_match_tabs(),
            'return_url': return_url,
            'filter_form': self.filterset_form(request.GET) if self.filterset_form else None,
            **self.get_extra_context(request),
        })

    def post(self, request, *args, **kwargs):
        logger = logging.getLogger('csaf.views.CsafMatchListView')
        logger.debug("POST from Match List")

        user = request.user
        if not user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        redirect_to_confirmed = False
        redirect_to_potential = False
        reject = request.POST.get('reject', "")
        if reject:
            setAcceptedStatusFor(self.queryset, reject, models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE, request)

        accept = request.POST.get('accept', "")
        if accept:
            setAcceptedStatusFor(self.queryset, accept, models.CsafMatch.AcceptanceStatus.CONFIRMED, request)
            redirect_to_confirmed = True

        renew = request.POST.get('renew', "")
        if renew:
            setAcceptedStatusFor(self.queryset, renew, models.CsafMatch.AcceptanceStatus.NEW, request)
            redirect_to_potential = True

        targetAccStatus = request.POST.get('targetAccStatus', "")
        if targetAccStatus:
            if targetAccStatus not in models.CsafMatch.AcceptanceStatus:
                messages.error(request, f"Unknown CSAF-Match AcceptanceStatus: {targetAccStatus}.")
                return self.get(request, args, kwargs)

            pk = request.POST.get('pk', None)
            pks = request.POST.getlist('pk', [pk])
            setAcceptedStatusFor(self.queryset, pks, targetAccStatus, request)
            if targetAccStatus == models.CsafMatch.AcceptanceStatus.CONFIRMED:
                redirect_to_confirmed = True
            elif targetAccStatus in (
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.REOPENED,
            ):
                redirect_to_potential = True

        targetRemStatus = request.POST.get('targetRemStatus', "")
        if targetRemStatus:
            if targetRemStatus not in models.CsafMatch.RemediationStatus:
                messages.error(request, f"Unknown CSAF-Match RemediationStatus: {targetRemStatus}.")
                return self.get(request, args, kwargs)

            selected_objects, _, _ = self.get_list_queryset(request)
            selected_objects = selected_objects.filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                skipped = 0
                for csafMatch in selected_objects.select_related('csaf_document'):
                    if csafMatch.acceptance_status != models.CsafMatch.AcceptanceStatus.CONFIRMED:
                        skipped += 1
                        continue
                    csafMatch.set_all_vulnerability_remediations(targetRemStatus)
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")
            if skipped:
                messages.warning(request, f"Skipped {skipped} non-confirmed CSAF-Matches.")
        if redirect_to_confirmed:
            return redirect('plugins:csaf:csafmatch_confirmed')
        if redirect_to_potential:
            return redirect('plugins:csaf:csafmatch_list')
        return redirect(self.get_return_url(request))


def setAcceptedStatusFor(queryset, matchId, targetStatus, request):
    if isinstance(matchId, (str, int)):
        selected_objects = queryset.filter(
            pk=matchId,
        )
    else:
        selected_objects = queryset.filter(
            pk__in=matchId,
        )
    with transaction.atomic():
        count = 0
        for csafMatch in selected_objects:
            csafMatch.acceptance_status = targetStatus
            csafMatch.save()
            count += 1
            # ToDo: Add config check if findings need to be created
            if targetStatus == models.CsafMatch.AcceptanceStatus.CONFIRMED:
                doc = csafMatch.csaf_document
                data = gatherProductInfoFromDoc(doc, csafMatch.product_name_id)
                createFindingsFromData(csafMatch, data)
    messages.success(request, f"Updated {count} CSAF-Matches")


def createFindingsFromData(match, data):
    # ToDo: Create finding
    pass


def gatherProductInfoFromDoc(doc, productNameId):
    if not doc.product_tree:
        return None
    for branch in doc.product_tree.get('branches', []):
        found, data = gatherProductInfoFromBranch(branch, productNameId)
        if found:
            return data
    return {}


def gatherProductInfoFromBranch(branch, productNameId):
    if getFromJson(branch, ('product', 'product_id', ), None) == productNameId:
        data = {}
        addDataFromBranch(branch.get('product'), data)
        addDataFromBranch(branch, data)
        return True, data
    for sub in branch.get('branches', []):
        found, data = gatherProductInfoFromBranch(sub, productNameId)
        if found:
            addDataFromBranch(branch, data)
            return found, data
    return False, {}


def addDataFromBranch(branch, data):
    if branch.get('category'):
        category = branch.get('category', None)
        if category and not data.get(category):
            data[category] = branch.get('name')
    if branch.get('product_id'):
        data['product_name'] = branch.get('name')


# CsafMatches view for New/Reopened Matches
@register_model_view(models.CsafMatch, name='confirmed', path='confirmed', detail=False)
class CsafConfirmedMatchListView(CsafMatchListView):
    status_filter_enabled = False
    include_confirmed_in_status_filter = True
    view_mode = 'confirmed'


class CsafMatchListFor(generic.ObjectChildrenView, GetReturnURLMixin):
    child_model = models.CsafMatch
    filterset = filtersets.CsafMatchFilterSet
    base_template = 'generic/object_children.html'
    template_name = 'csaf/csafmatch_list.html'
    linkName = 'None'
    comparison_column_mode = 'hide'

    def apply_comparison_column_layout(self, table):
        if 'comparison' not in table.columns.names():
            return

        if self.comparison_column_mode == 'hide':
            table.columns.hide('comparison')
            return

        table.columns.show('comparison')
        sequence = [name for name in table.sequence if name != 'comparison']
        if 'actions' in sequence:
            actions_index = sequence.index('actions')
            sequence.insert(actions_index, 'comparison')
        else:
            sequence.append('comparison')
        table.sequence = sequence

    def get_children_for(self, parent):
        return self.child_model.objects.select_related(
            'device',
            'module',
            'software',
            'csaf_document',
        ).prefetch_related('csaf_document__vulnerabilities', 'vulnerability_statuses')

    def get_confirmed_tab_url(self, instance):
        base = instance.get_absolute_url()
        if not base.endswith('/'):
            base += '/'
        return f'{base}csafmatches/'

    def get_potential_tab_url(self, instance):
        base = instance.get_absolute_url()
        if not base.endswith('/'):
            base += '/'
        return f'{base}csafmatchesnew/'

    def post(self, request, *args, **kwargs):
        logger = logging.getLogger('csaf.views.CsafMatchListFor')
        logger.debug("POST from Match List")
        instance = self.get_object(**kwargs)

        children = self.get_children_for(instance)
        user = request.user
        if not user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        redirect_to_confirmed = False
        redirect_to_potential = False
        reject = request.POST.get('reject', "")
        if reject:
            setAcceptedStatusFor(children, reject, models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE, request)

        accept = request.POST.get('accept', "")
        if accept:
            setAcceptedStatusFor(children, accept, models.CsafMatch.AcceptanceStatus.CONFIRMED, request)
            redirect_to_confirmed = True

        renew = request.POST.get('renew', "")
        if renew:
            setAcceptedStatusFor(children, renew, models.CsafMatch.AcceptanceStatus.NEW, request)
            redirect_to_potential = True

        targetAccStatus = request.POST.get('targetAccStatus', "")
        if targetAccStatus:
            if targetAccStatus not in models.CsafMatch.AcceptanceStatus:
                messages.error(request, f"Unknown CSAF-Match AcceptanceStatus: {targetAccStatus}.")
                return redirect(self.get_return_url(request))

            selected_objects = children.filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                for csafMatch in selected_objects:
                    csafMatch.acceptance_status = targetAccStatus
                    csafMatch.save()
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")
            if targetAccStatus == models.CsafMatch.AcceptanceStatus.CONFIRMED:
                redirect_to_confirmed = True
            elif targetAccStatus in (
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.REOPENED,
            ):
                redirect_to_potential = True

        targetRemStatus = request.POST.get('targetRemStatus', "")
        if targetRemStatus:
            if targetRemStatus not in models.CsafMatch.RemediationStatus:
                messages.error(request, f"Unknown CSAF-Match RemediationStatus: {targetRemStatus}.")
                return redirect(self.get_return_url(request))

            selected_objects = children.filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                skipped = 0
                for csafMatch in selected_objects.select_related('csaf_document'):
                    if csafMatch.acceptance_status != models.CsafMatch.AcceptanceStatus.CONFIRMED:
                        skipped += 1
                        continue
                    csafMatch.set_all_vulnerability_remediations(targetRemStatus)
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")
            if skipped:
                messages.warning(request, f"Skipped {skipped} non-confirmed CSAF-Matches.")
        if redirect_to_confirmed:
            return redirect(self.get_confirmed_tab_url(instance))
        if redirect_to_potential:
            return redirect(self.get_potential_tab_url(instance))
        return redirect(self.get_return_url(request))


    def get(self, request, *args, **kwargs):
        instance = self.get_object(**kwargs)
        statusString, acceptance_status, statusSearch = handleStatus(request)
        childObjects = self.get_children_for(instance) #.filter(acceptance_status__in=statusSearch)
        if self.filterset:
            childObjects = self.filterset(request.GET, childObjects, request=request).qs

        # Determine the available actions
        actions = self.get_permitted_actions(request.user, model=self.child_model)
        has_bulk_actions = any([a.startswith('bulk_') for a in actions])

        table_data = self.prep_table_data(request, childObjects, instance)
        table = self.get_table(table_data, request, has_bulk_actions)
        self.apply_comparison_column_layout(table)

        # If this is an HTMX request, return only the rendered table HTML
        if htmx_partial(request):
            return render(request, 'htmx/table.html', {
                'object': instance,
                'table': table,
                'model': self.child_model,
            })

        return_url = cleanUrl(request.get_full_path())
        return render(request, self.get_template_name(), {
            'object': instance,
            'link_name': self.linkName,
            'model': self.child_model,
            'child_model': self.child_model,
            'base_template': f'{instance._meta.app_label}/{instance._meta.model_name}.html',
            'table': table,
            'table_config': f'{table.name}_config',
            'table_configs': get_table_configs(table, request.user),
            'actions': actions,
            'tab': self.tab,
            'acceptance_status': acceptance_status,
            'statusString': statusString,
            'enums': {'acceptance': models.CsafMatch.AcceptanceStatus, 'remediation': models.CsafMatch.RemediationStatus},
            'return_url': return_url,
            **self.get_extra_context(request, instance),
        })


def cleanUrl(url):
    parts = url.split('?')
    if len(parts) == 1:
        return parts[0] + '?'
    result = parts[0] + '?'
    parts = parts[1].split('&')
    for part in parts:
        if not part.strip():
            continue
        if not (
            part.startswith('statusString')
            or part.startswith('toggle')
            or part.startswith('remStatusString')
            or part.startswith('remToggle')
            or part.startswith('include_false_positives')
        ):
            result = result + part + '&'
    return result


def extract_csaf_products(product_tree):
    products = []
    known_branch_categories = {
        'architecture',
        'host_name',
        'language',
        'legacy',
        'patch_level',
        'product_family',
        'product_name',
        'product_version',
        'product_version_range',
        'service_pack',
        'specification',
        'vendor',
    }

    def walk(node, path, lineage):
        if isinstance(node, dict):
            category = node.get('category')
            name = node.get('name')
            include_in_lineage = category in known_branch_categories and isinstance(name, str) and bool(name.strip())
            current_path = path + ([name] if include_in_lineage else [])
            current_lineage = lineage + ([{'category': category, 'name': name}] if include_in_lineage else [])

            product = node.get('product')
            if isinstance(product, dict):
                entry = dict(product)
                entry['_branch_category'] = category
                entry['_branch_name'] = name
                if current_path:
                    entry['path'] = current_path
                if current_lineage:
                    entry['_lineage'] = current_lineage
                products.append(entry)

            full_product_names = node.get('full_product_names')
            if isinstance(full_product_names, list):
                for item in full_product_names:
                    if isinstance(item, dict):
                        entry = dict(item)
                        entry['_branch_category'] = category
                        entry['_branch_name'] = name
                        if current_path:
                            entry['path'] = current_path
                        if current_lineage:
                            entry['_lineage'] = current_lineage
                        products.append(entry)

            if 'product_id' in node and 'name' in node and category in known_branch_categories:
                entry = dict(node)
                entry['_branch_category'] = category
                entry['_branch_name'] = name
                if current_path:
                    entry['path'] = current_path
                if current_lineage:
                    entry['_lineage'] = current_lineage
                products.append(entry)

            for branch in node.get('branches', []) or []:
                walk(branch, current_path, current_lineage)
        elif isinstance(node, list):
            for item in node:
                walk(item, path, lineage)

    walk(product_tree or {}, [], [])
    return products


def get_product_for_match(match):
    target_product_id = (match.product_name_id or '').strip()
    if not target_product_id:
        return None

    for product in extract_csaf_products(match.csaf_document.product_tree):
        if str(product.get('product_id', '')).strip() == target_product_id:
            return product
    return None


def get_type_version_value(type_obj):
    if type_obj is None:
        return None

    try:
        type_obj._meta.get_field('hardware_version')
        value = getattr(type_obj, 'hardware_version', None)
        if value not in (None, ''):
            return value
    except FieldDoesNotExist:
        pass

    try:
        type_obj._meta.get_field('version')
        value = getattr(type_obj, 'version', None)
        if value not in (None, ''):
            return value
    except FieldDoesNotExist:
        pass

    if has_custom_field(type_obj, 'hardware_version'):
        value = (getattr(type_obj, 'custom_field_data', {}) or {}).get('hardware_version')
        if value not in (None, ''):
            return value

    if has_custom_field(type_obj, 'hardware_name'):
        value = (getattr(type_obj, 'custom_field_data', {}) or {}).get('hardware_name')
        if value not in (None, ''):
            return value
    return None


def get_match_asset_fields(match):
    asset = match.related_asset
    base = {
        'Asset Type': match.related_asset_type,
        'Asset': str(asset) if asset else '-',
        'Product ID': match.product_name_id,
    }

    if match.device is not None:
        device = match.device
        device_type = getattr(device, 'device_type', None)
        manufacturer = getattr(device_type, 'manufacturer', None)
        type_version = get_type_version_value(device_type)
        return {
            **base,
            'Name': getattr(device, 'name', None),
            'Manufacturer': getattr(manufacturer, 'name', None),
            'Model': getattr(device_type, 'model', None),
            'Version': type_version,
            'Part Number': getattr(device_type, 'part_number', None),
            'Serial': getattr(device, 'serial', None),
            'Asset Tag': getattr(device, 'asset_tag', None),
            'Platform': str(device.platform) if getattr(device, 'platform', None) else None,
        }

    if match.module is not None:
        module = match.module
        module_type = getattr(module, 'module_type', None)
        manufacturer = getattr(module_type, 'manufacturer', None)
        type_version = get_type_version_value(module_type)
        return {
            **base,
            'Name': str(module),
            'Manufacturer': getattr(manufacturer, 'name', None),
            'Model': getattr(module_type, 'model', None),
            'Version': type_version,
            'Part Number': getattr(module_type, 'part_number', None),
            'Serial': getattr(module, 'serial', None),
            'Asset Tag': getattr(module, 'asset_tag', None),
        }

    if match.software is not None:
        software = match.software
        manufacturer = getattr(software, 'manufacturer', None)
        return {
            **base,
            'Name': getattr(software, 'name', None),
            'Manufacturer': str(manufacturer) if manufacturer else None,
            'Version': getattr(software, 'version', None),
            'CPE': getattr(software, 'cpe', None),
            'PURL': getattr(software, 'purl', None),
            'Firmware': getattr(software, 'is_firmware', None),
        }

    return base


def get_product_fields(product):
    if not isinstance(product, dict):
        return {}
    helper = product.get('product_identification_helper') or {}
    if not isinstance(helper, dict):
        helper = {}
    lineage = product.get('_lineage') or []
    if not isinstance(lineage, list):
        lineage = []

    def first_list_value(value):
        if isinstance(value, list) and value:
            return value[0]
        return None

    def branch_name_by_category(*categories):
        for category in categories:
            for entry in reversed(lineage):
                if not isinstance(entry, dict):
                    continue
                if entry.get('category') == category and entry.get('name'):
                    return entry.get('name')
        return None

    path = product.get('path') or []
    vendor_name = branch_name_by_category('vendor')
    product_name_branch = branch_name_by_category('product_name', 'product_family')
    version_branch = branch_name_by_category(
        'product_version_range',
        'product_version',
        'service_pack',
        'patch_level',
    )
    model_number = first_list_value(helper.get('model_numbers'))
    sku = first_list_value(helper.get('skus'))
    serial_number = first_list_value(helper.get('serial_numbers'))

    return {
        'Product ID': product.get('product_id'),
        'Name': product_name_branch or product.get('name'),
        'Path': ' > '.join(path) if path else None,
        'Manufacturer': vendor_name,
        'CPE': helper.get('cpe'),
        'PURL': helper.get('purl'),
        'SKU': sku,
        'Serial Number': serial_number,
        'Model': model_number or product_name_branch,
        'Version': version_branch,
        'Canonical Product Name': product.get('name'),
    }


def build_match_comparison_rows(asset_fields, product_fields):
    rows = []

    def make_row(field_key, field_label, asset_value, product_value):
        rows.append({
            'field_key': field_key,
            'field': field_label,
            'asset_value': asset_value if asset_value not in (None, '') else '-',
            'product_value': product_value if product_value not in (None, '') else '-',
            'asset_raw': asset_value,
            'product_raw': product_value,
            'is_identical': asset_value == product_value,
        })

    make_row('name', 'Name', asset_fields.get('Name'), product_fields.get('Name'))
    make_row('manufacturer', 'Manufacturer', asset_fields.get('Manufacturer'), product_fields.get('Manufacturer'))
    make_row('model', 'Model', asset_fields.get('Model'), product_fields.get('Model'))
    make_row('part_number', 'Part Number', asset_fields.get('Part Number'), product_fields.get('SKU'))
    make_row('version', 'Version', asset_fields.get('Version'), product_fields.get('Version'))
    make_row('cpe', 'CPE', asset_fields.get('CPE'), product_fields.get('CPE'))
    make_row('purl', 'PURL', asset_fields.get('PURL'), product_fields.get('PURL'))
    make_row('serial', 'Serial', asset_fields.get('Serial'), product_fields.get('Serial Number'))

    return rows


def get_transfer_mapping_for_match(match):
    if match.device is not None:
        mapping = {
            'name': {'target': 'asset', 'attr': 'name', 'kind': 'string'},
            'serial': {'target': 'asset', 'attr': 'serial', 'kind': 'string'},
            'manufacturer': {'target': 'device_type', 'attr': 'manufacturer', 'kind': 'manufacturer_fk'},
            'model': {'target': 'device_type', 'attr': 'model', 'kind': 'string'},
            'part_number': {'target': 'device_type', 'attr': 'part_number', 'kind': 'string'},
        }
        device_type = getattr(match.device, 'device_type', None)
        try:
            if device_type is not None:
                device_type._meta.get_field('hardware_version')
                mapping['version'] = {'target': 'device_type', 'attr': 'hardware_version', 'kind': 'string'}
        except FieldDoesNotExist:
            try:
                if device_type is not None:
                    device_type._meta.get_field('version')
                    mapping['version'] = {'target': 'device_type', 'attr': 'version', 'kind': 'string'}
            except FieldDoesNotExist:
                if has_custom_field(device_type, 'hardware_version'):
                    mapping['version'] = {
                        'target': 'device_type',
                        'kind': 'custom_field',
                        'custom_field_name': 'hardware_version',
                    }
                elif has_custom_field(device_type, 'hardware_name'):
                    # Backward compatibility for existing setups still using "hardware_name".
                    mapping['version'] = {
                        'target': 'device_type',
                        'kind': 'custom_field',
                        'custom_field_name': 'hardware_name',
                    }
        return mapping
    if match.module is not None:
        mapping = {
            'serial': {'target': 'asset', 'attr': 'serial', 'kind': 'string'},
            'manufacturer': {'target': 'module_type', 'attr': 'manufacturer', 'kind': 'manufacturer_fk'},
            'model': {'target': 'module_type', 'attr': 'model', 'kind': 'string'},
            'part_number': {'target': 'module_type', 'attr': 'part_number', 'kind': 'string'},
        }
        module_type = getattr(match.module, 'module_type', None)
        try:
            if module_type is not None:
                module_type._meta.get_field('hardware_version')
                mapping['version'] = {'target': 'module_type', 'attr': 'hardware_version', 'kind': 'string'}
        except FieldDoesNotExist:
            try:
                if module_type is not None:
                    module_type._meta.get_field('version')
                    mapping['version'] = {'target': 'module_type', 'attr': 'version', 'kind': 'string'}
            except FieldDoesNotExist:
                if has_custom_field(module_type, 'hardware_version'):
                    mapping['version'] = {
                        'target': 'module_type',
                        'kind': 'custom_field',
                        'custom_field_name': 'hardware_version',
                    }
                elif has_custom_field(module_type, 'hardware_name'):
                    # Backward compatibility for existing setups still using "hardware_name".
                    mapping['version'] = {
                        'target': 'module_type',
                        'kind': 'custom_field',
                        'custom_field_name': 'hardware_name',
                    }
        return mapping
    if match.software is not None:
        return {
            'name': {'target': 'asset', 'attr': 'name', 'kind': 'string'},
            'manufacturer': {'target': 'asset', 'attr': 'manufacturer', 'kind': 'manufacturer_fk'},
            'version': {'target': 'asset', 'attr': 'version', 'kind': 'string'},
            'cpe': {'target': 'asset', 'attr': 'cpe', 'kind': 'string'},
            'purl': {'target': 'asset', 'attr': 'purl', 'kind': 'string'},
        }
    return {}


def get_transfer_target_object(match, target_label):
    if target_label == 'asset':
        return match.related_asset
    if target_label == 'device_type' and match.device is not None:
        return getattr(match.device, 'device_type', None)
    if target_label == 'module_type' and match.module is not None:
        return getattr(match.module, 'module_type', None)
    return None


def is_type_level_transfer_target(target_label):
    return target_label in ('device_type', 'module_type')


def has_change_permission_for_object(user, obj):
    if obj is None:
        return False
    return user.has_perm(f'{obj._meta.app_label}.change_{obj._meta.model_name}')


def has_custom_field(obj, field_name):
    if obj is None:
        return False
    return obj.custom_fields.filter(name=field_name).exists()


def can_edit_related_asset(user, match):
    mapping = get_transfer_mapping_for_match(match)
    if not mapping:
        return False
    for spec in mapping.values():
        target_obj = get_transfer_target_object(match, spec.get('target'))
        if has_change_permission_for_object(user, target_obj):
            return True
    return False


def transfer_product_value_to_asset(match, field_key, comparison_rows, transfer_value=None, actor_user=None):
    mapping = get_transfer_mapping_for_match(match)
    spec = mapping.get(field_key)
    if not spec:
        return False, 'This field is not transferable for the matched asset type.'
    target_label = spec.get('target')
    target_obj = get_transfer_target_object(match, target_label)
    target_attr = spec.get('attr')
    value_kind = spec.get('kind', 'string')
    custom_field_name = spec.get('custom_field_name')

    if target_obj is None:
        return False, 'Could not resolve transfer target for this field.'

    row = next((entry for entry in comparison_rows if entry['field_key'] == field_key), None)
    if row is None:
        return False, 'Unknown comparison field.'

    value = transfer_value if transfer_value is not None else row.get('product_raw')
    if value in (None, ''):
        return False, 'The CSAF product field is empty and cannot be transferred.'

    if value_kind == 'manufacturer_fk':
        value_str = str(value).strip()
        if not value_str:
            return False, 'Manufacturer value is empty.'

        current_manufacturer = getattr(target_obj, target_attr, None)
        if current_manufacturer is not None:
            if actor_user is not None and not has_change_permission_for_object(actor_user, current_manufacturer):
                return False, 'Missing permission to edit the linked manufacturer object.'
            current_manufacturer.name = value_str
            current_manufacturer.save(update_fields=['name'])
            changed_field = f'{target_attr}.name'
        else:
            manufacturer = Manufacturer.objects.filter(name__iexact=value_str).first()
            if manufacturer is None:
                return False, f'No manufacturer named "{value_str}" exists in NetBox.'
            setattr(target_obj, target_attr, manufacturer)
            target_obj.save(update_fields=[target_attr])
            changed_field = target_attr
    elif value_kind == 'custom_field':
        if not custom_field_name:
            return False, 'Invalid custom field transfer configuration.'
        if not has_custom_field(target_obj, custom_field_name):
            return False, f'Custom field "{custom_field_name}" is not configured for this object.'
        custom_field_data = dict(getattr(target_obj, 'custom_field_data', {}) or {})
        custom_field_data[custom_field_name] = value
        target_obj.custom_field_data = custom_field_data
        target_obj.save(update_fields=['custom_field_data'])
        changed_field = f'custom_field_data.{custom_field_name}'
    else:
        if not target_attr:
            return False, 'Invalid transfer target field.'
        setattr(target_obj, target_attr, value)
        target_obj.save(update_fields=[target_attr])
        changed_field = target_attr

    if is_type_level_transfer_target(target_label):
        return True, (
            f'Updated {target_obj._meta.verbose_name} field "{changed_field}" from CSAF product data. '
            'This changed a type definition, not only a single instance.'
        )
    return True, f'Updated {target_obj._meta.verbose_name} field "{changed_field}" from CSAF product data.'


@register_model_view(models.CsafMatch, name='comparison', path='comparison')
class CsafMatchComparisonView(generic.ObjectView):
    queryset = models.CsafMatch.objects.select_related(
        'device',
        'device__device_type',
        'device__device_type__manufacturer',
        'module',
        'module__module_type',
        'module__module_type__manufacturer',
        'software',
        'software__manufacturer',
        'csaf_document',
    )
    template_name = 'csaf/csafmatch_comparison.html'

    def render_comparison_page(self, request, instance, transfer_edit_field='', transfer_edit_value=''):
        product = get_product_for_match(instance)
        asset_fields = get_match_asset_fields(instance)
        product_fields = get_product_fields(product)
        comparison_rows = build_match_comparison_rows(asset_fields, product_fields)
        transfer_mapping = get_transfer_mapping_for_match(instance)
        can_transfer = can_edit_related_asset(request.user, instance)

        for row in comparison_rows:
            row_spec = transfer_mapping.get(row['field_key'])
            row_target = get_transfer_target_object(instance, row_spec.get('target')) if row_spec else None
            has_target_permission = has_change_permission_for_object(request.user, row_target)
            if row_spec and row_spec.get('kind') == 'manufacturer_fk' and row_target is not None:
                linked_manufacturer = getattr(row_target, row_spec.get('attr'), None)
                if linked_manufacturer is not None:
                    has_target_permission = has_target_permission and has_change_permission_for_object(
                        request.user, linked_manufacturer
                    )
            row['edits_type_definition'] = bool(row_spec and is_type_level_transfer_target(row_spec.get('target')))
            row['transferable'] = bool(
                row_spec is not None
                and has_target_permission
                and row['product_raw'] not in (None, '')
                and not row['is_identical']
            )
            if transfer_edit_field and row['field_key'] == transfer_edit_field:
                row['edit_value'] = transfer_edit_value if transfer_edit_value is not None else row['product_raw']
            else:
                row['edit_value'] = row['product_raw']

        return render(request, self.get_template_name(), {
            'object': instance,
            'asset': instance.related_asset,
            'tab': self.tab,
            'asset_fields': asset_fields,
            'product_fields': product_fields,
            'comparison_rows': comparison_rows,
            'product': product,
            'can_transfer': can_transfer,
            'transfer_edit_field': transfer_edit_field,
            **self.get_extra_context(request, instance),
        })

    def post(self, request, **kwargs):
        instance = self.get_object(**kwargs)
        action = request.POST.get('transfer_action', '')
        field_key = request.POST.get('transfer_field', '')
        if not field_key:
            messages.error(request, 'Missing transfer field.')
            return redirect(request.path)
        mapping = get_transfer_mapping_for_match(instance)
        spec = mapping.get(field_key)
        if not spec:
            messages.error(request, 'This field is not transferable.')
            return redirect(request.path)
        target_obj = get_transfer_target_object(instance, spec.get('target'))
        if not has_change_permission_for_object(request.user, target_obj):
            return self.handle_no_permission()

        if action == 'prepare':
            transfer_value = request.POST.get('transfer_value')
            return self.render_comparison_page(
                request,
                instance,
                transfer_edit_field=field_key,
                transfer_edit_value=transfer_value,
            )

        if action == 'apply':
            transfer_value = request.POST.get('transfer_value')
            if is_type_level_transfer_target(spec.get('target')):
                messages.warning(
                    request,
                    'You are editing a type definition (Device Type / Module Type), not only this single instance.',
                )
            comparison_rows = build_match_comparison_rows(
                get_match_asset_fields(instance),
                get_product_fields(get_product_for_match(instance)),
            )
            ok, msg = transfer_product_value_to_asset(
                instance,
                field_key,
                comparison_rows,
                transfer_value=transfer_value,
                actor_user=request.user,
            )
            if ok:
                messages.success(request, msg)
            else:
                messages.error(request, msg)
            return redirect(request.path)

        messages.error(request, 'Unknown transfer action.')
        return redirect(request.path)

    def get(self, request, **kwargs):
        instance = self.get_object(**kwargs)
        return self.render_comparison_page(request, instance)





# New CsafMatches view for one Device
@register_model_view(Device, name='newcsafmatchlistfordeviceview', path='csafmatchesnew', )
class CsafNewMatchListForDeviceView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Device.objects.all()
    table = tables.CsafMatchListForDeviceTable
    linkName= 'device'
    comparison_column_mode = 'hide'

    tab = ViewTab(
        label='Potential CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            device=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.REOPENED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                device=parent
            ).filter(
                acceptance_status__in=[
                    models.CsafMatch.AcceptanceStatus.NEW,
                    models.CsafMatch.AcceptanceStatus.REOPENED
                ]
            )


# Confirmed CsafMatches view for one Device
@register_model_view(Device, name='csafmatchlistfordeviceview', path='csafmatches', )
class CsafConfirmedMatchListForDeviceView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Device.objects.all()
    table = tables.CsafMatchListForDeviceTable
    linkName= 'device'
    comparison_column_mode = 'rightmost'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            device=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.CONFIRMED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                device=parent
            ).filter(
                acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
            )


# New CsafMatches view for one Module
@register_model_view(Module, name='newcsafmatchlistformoduleview', path='csafmatchesnew', )
class CsafNewMatchListForModuleView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Module. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Module.objects.all()
    table = tables.CsafMatchListForModuleTable
    linkName= 'module'
    comparison_column_mode = 'hide'

    tab = ViewTab(
        label='Potential CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            module=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.REOPENED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                module=parent
            ).filter(
                acceptance_status__in=[
                    models.CsafMatch.AcceptanceStatus.NEW,
                    models.CsafMatch.AcceptanceStatus.REOPENED
                ]
            )


# Confirmed CsafMatches view for one Module
@register_model_view(Module, name='csafmatchlistformoduleview', path='csafmatches', )
class CsafMatchListForModuleView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Module. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Module.objects.all()
    table = tables.CsafMatchListForModuleTable
    linkName= 'module'
    comparison_column_mode = 'rightmost'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            module=obj,
            acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                module=parent
            ).filter(
                acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
            )


# New CsafMatches view for one Document
@register_model_view(model=models.CsafDocument, name='newmatchlistforcsafdocument', path='csafmatchesnew', )
class CsafNewMatchListForCsafDocumentView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a CsafDocument. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafMatchListForCsafDocumentTable
    linkName= 'document'
    comparison_column_mode = 'hide'

    tab = ViewTab(
        label='Potential CSAF Matches',
        badge=lambda obj: (
            lambda new_count, reopened_count, false_positives:
                f"{new_count + reopened_count} | R:{reopened_count}"
                + (f" | FP:{false_positives}" if false_positives else "")
        )(
            models.CsafMatch.objects.filter(
                csaf_document=obj,
                acceptance_status=models.CsafMatch.AcceptanceStatus.NEW,
            ).count(),
            models.CsafMatch.objects.filter(
                csaf_document=obj,
                acceptance_status=models.CsafMatch.AcceptanceStatus.REOPENED,
            ).count(),
            models.CsafMatch.objects.filter(
                csaf_document=obj,
                acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE,
            ).count(),
        ),
        permission='csaf.view_csafmatch'
    )

    def _set_include_false_positives(self, request):
        self.include_false_positives = parseBool(request.GET.get('include_false_positives', None)) is True

    def get(self, request, *args, **kwargs):
        self._set_include_false_positives(request)
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self._set_include_false_positives(request)
        return super().post(request, *args, **kwargs)

    def get_children_for(self, parent):
        statuses = [
            models.CsafMatch.AcceptanceStatus.NEW,
            models.CsafMatch.AcceptanceStatus.REOPENED,
        ]
        if getattr(self, 'include_false_positives', False):
            statuses.append(models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)
        return self.child_model.objects.filter(
                csaf_document=parent
            ).filter(
                acceptance_status__in=statuses
            )

    def get_extra_context(self, request, instance):
        false_positive_count = self.child_model.objects.filter(
            csaf_document=instance,
            acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE,
        ).count()
        return {
            'false_positive_count': false_positive_count,
            'include_false_positives': getattr(self, 'include_false_positives', False),
        }


# Confirmed CsafMatches view for one Document
@register_model_view(model=models.CsafDocument, name='matchlistforcsafdocument', path='csafmatches', )
class CsafMatchListForCsafDocumentView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a CsafDocument. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafMatchListForCsafDocumentTable
    linkName= 'document'
    comparison_column_mode = 'rightmost'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            csaf_document=obj,
            acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                csaf_document=parent
            ).filter(
                acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
            )


# CsafVulnerabilities view for one Document
@register_model_view(model=models.CsafDocument, name='vulnerabilitylistforcsafdocument', path='vulnerabilities', )
class CsafVulnerabilityListForCsafDocumentView(generic.ObjectChildrenView):
    """ Handles the request of displaying vulnerabilities associated to a CsafDocument. """
    additional_permissions = ('csaf.view_csafvulnerability',)
    queryset = models.CsafDocument.objects.all()
    child_model = models.CsafVulnerability
    table = tables.CsafVulnerabilityTable
    filterset = filtersets.CsafVulnerabilityFilterSet
    filterset_form = forms.CsafVulnerabilityFilterForm

    tab = ViewTab(
        label='Vulnerabilities',
        badge=lambda obj: models.CsafVulnerability.objects.filter(csaf_document=obj).count(),
        permission='csaf.view_csafvulnerability'
    )

    def get_children(self, request, parent):
        return self.child_model.objects.filter(csaf_document=parent)


# New CsafMatches view for one Software
@register_model_view(model=Software, name='newmatchlistforsoftware', path='csafmatchesnew', )
class CsafMatchListForSoftwareView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Software Entity. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Software.objects.all()
    table = tables.CsafMatchListForSoftwareTable
    linkName= 'software'
    comparison_column_mode = 'hide'

    tab = ViewTab(
        label='Potential CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            software=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.CONFIRMED,
                models.CsafMatch.AcceptanceStatus.REOPENED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(software=parent)


# Confirmed CsafMatches view for one Software
@register_model_view(model=Software, name='matchlistforsoftware', path='csafmatches', )
class CsafMatchListForSoftwareView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Software Entity. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Software.objects.all()
    table = tables.CsafMatchListForSoftwareTable
    linkName= 'software'
    comparison_column_mode = 'rightmost'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            software=obj,
            acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                software=parent
            ).filter(
                acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
            )


class CsafVulnerabilityListForAsset(generic.ObjectChildrenView, GetReturnURLMixin):
    """
    Handles asset-specific vulnerability entries derived from CSAF matches.
    """
    additional_permissions = ('csaf.view_csafmatch',)
    child_model = models.CsafMatchVulnerabilityRemediation
    table = tables.CsafAssetVulnerabilityTable
    template_name = 'csaf/csaf_asset_vulnerability_list.html'

    def get_children_for(self, parent):
        return self.child_model.objects.none()

    def get_current_page_url(self, request):
        query = request.GET.urlencode()
        if query:
            return f'{request.path}?{query}'
        return request.path

    def get_remediation_filter(self, request):
        status = {}
        idx = 0
        status_string = request.GET.get('remStatusString', '111')
        for entry in models.CsafMatch.RemediationStatus:
            status[str(entry)] = int(status_string[idx]) if idx < len(status_string) else 1
            idx += 1

        toggle = request.GET.get('remToggle', "")
        if toggle in status:
            status[toggle] = 1 - int(status[toggle])

        status_string = "".join(str(status[str(entry)]) for entry in models.CsafMatch.RemediationStatus)
        status_search = {s for s, v in status.items() if v}
        if not status_search:
            status_search = {str(entry) for entry in models.CsafMatch.RemediationStatus}

        filter_buttons = [
            {
                'value': entry.value,
                'label': entry.label,
                'active': bool(status[str(entry)]),
            }
            for entry in models.CsafMatch.RemediationStatus
        ]
        return status_string, status_search, filter_buttons

    def get(self, request, *args, **kwargs):
        instance = self.get_object(**kwargs)
        child_objects = self.get_children_for(instance)
        rem_status_string, rem_status_search, rem_filter_buttons = self.get_remediation_filter(request)
        child_objects = child_objects.filter(remediation_status__in=rem_status_search)

        table = self.get_table(child_objects, request, False)

        if htmx_partial(request):
            return render(request, 'htmx/table.html', {
                'object': instance,
                'table': table,
                'model': self.child_model,
            })

        return_url = cleanUrl(request.get_full_path())
        return render(request, self.get_template_name(), {
            'object': instance,
            'model': self.child_model,
            'child_model': self.child_model,
            'base_template': f'{instance._meta.app_label}/{instance._meta.model_name}.html',
            'table': table,
            'table_config': f'{table.name}_config',
            'table_configs': get_table_configs(table, request.user),
            'actions': (),
            'tab': self.tab,
            'return_url': return_url,
            'rem_status_string': rem_status_string,
            'rem_filter_buttons': rem_filter_buttons,
            **self.get_extra_context(request, instance),
        })

    def post(self, request, *args, **kwargs):
        instance = self.get_object(**kwargs)
        if not request.user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        return_url = self.get_current_page_url(request)
        payload = request.POST.get('vuln_update', '')
        if not payload:
            messages.error(request, "Missing vulnerability remediation update data.")
            return redirect(return_url)

        payload_parts = payload.split(':', 1)
        if len(payload_parts) != 2:
            messages.error(request, "Invalid vulnerability remediation update data.")
            return redirect(return_url)

        remediation_entry_id, remediation_status = payload_parts
        if remediation_status not in models.CsafMatch.RemediationStatus:
            messages.error(request, f"Unknown remediation status: {remediation_status}")
            return redirect(return_url)

        remediation_entry = self.get_children_for(instance).filter(pk=remediation_entry_id).select_related(
            'match',
            'vulnerability',
        ).first()
        if remediation_entry is None:
            messages.error(request, "Unknown vulnerability remediation entry.")
            return redirect(return_url)

        if remediation_entry.match.acceptance_status != models.CsafMatch.AcceptanceStatus.CONFIRMED:
            messages.error(request, "Remediation status can only be changed for confirmed matches.")
            return redirect(return_url)

        try:
            remediation_entry.match.set_vulnerability_remediation(remediation_entry.vulnerability, remediation_status)
        except ValueError as ex:
            messages.error(request, str(ex))
            return redirect(return_url)
        messages.success(request, "Updated vulnerability remediation status.")
        return redirect(return_url)


def vulnerability_tab_badge_for(**asset_filter):
    counts = models.CsafMatchVulnerabilityRemediation.objects.filter(
        match__acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED,
        **asset_filter,
    ).aggregate(
        not_started=Count(
            'id',
            filter=Q(remediation_status=models.CsafMatch.RemediationStatus.NEW),
        ),
        in_progress=Count(
            'id',
            filter=Q(remediation_status=models.CsafMatch.RemediationStatus.IN_PROGRESS),
        ),
        complete=Count(
            'id',
            filter=Q(remediation_status=models.CsafMatch.RemediationStatus.RESOLVED),
        ),
    )
    parts = []
    if counts['not_started']:
        parts.append(f"🔴{counts['not_started']}")
    if counts['in_progress']:
        parts.append(f"🟡{counts['in_progress']}")
    if counts['complete']:
        parts.append(f"🟢{counts['complete']}")
    return " ".join(parts)


@register_model_view(Device, name='vulnerabilitylistfordevice', path='csafvulnerabilities')
class CsafVulnerabilityListForDeviceView(CsafVulnerabilityListForAsset):
    """
    Handles the request for displaying vulnerabilities linked to matches for one Device.
    """
    queryset = Device.objects.all()

    tab = ViewTab(
        label='Vulnerabilities',
        badge=lambda obj: vulnerability_tab_badge_for(match__device=obj),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
            match__device=parent,
            match__acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED,
        ).select_related(
            'match',
            'vulnerability',
            'match__csaf_document',
            'match__device',
            'match__module',
            'match__software',
        )


@register_model_view(Module, name='vulnerabilitylistformodule', path='csafvulnerabilities')
class CsafVulnerabilityListForModuleView(CsafVulnerabilityListForAsset):
    """
    Handles the request for displaying vulnerabilities linked to matches for one Module.
    """
    queryset = Module.objects.all()

    tab = ViewTab(
        label='Vulnerabilities',
        badge=lambda obj: vulnerability_tab_badge_for(match__module=obj),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
            match__module=parent,
            match__acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED,
        ).select_related(
            'match',
            'vulnerability',
            'match__csaf_document',
            'match__device',
            'match__module',
            'match__software',
        )


@register_model_view(Software, name='vulnerabilitylistforsoftware', path='csafvulnerabilities')
class CsafVulnerabilityListForSoftwareView(CsafVulnerabilityListForAsset):
    """
    Handles the request for displaying vulnerabilities linked to matches for one Software.
    """
    queryset = Software.objects.all()

    tab = ViewTab(
        label='Vulnerabilities',
        badge=lambda obj: vulnerability_tab_badge_for(match__software=obj),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
            match__software=parent,
            match__acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED,
        ).select_related(
            'match',
            'vulnerability',
            'match__csaf_document',
            'match__device',
            'match__module',
            'match__software',
        )


def handleStatus(request, enumCls=models.CsafMatch.AcceptanceStatus, deflt='1110'):
    status = {
    }
    idx = 0;
    statusString = request.GET.get('statusString', deflt)
    for entry in enumCls:
        status[str(entry)] = int(statusString[idx])
        idx += 1
    toggle = request.GET.get('toggle', "")
    if toggle in status:
        status[toggle] = 1 - int(status[toggle])
    statusString = ""
    for entry in enumCls:
        statusString += str(status[str(entry)])
    statusSearch={0}
    for s,v in status.items():
        if v:
            statusSearch.add(s)
    return statusString,status,statusSearch


@register_model_view(Device, name='withmatches', path='withmatches', detail=False)
class DeviceListWithCsafMatches(generic.ObjectListView):
    """ This view handles the request for displaying Devices with CsafMatches as a table. """
    queryset = Device.objects.annotate(
            new_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .filter(acceptance_status__in=[
                        models.CsafMatch.AcceptanceStatus.NEW,
                        models.CsafMatch.AcceptanceStatus.REOPENED])
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            total_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).filter(total_count__gt=0)
    table = tables.DevicesWithMatchTable


@register_model_view(Module, name='withmatches', path='withmatches', detail=False)
class ModuleListWithCsafMatches(generic.ObjectListView):
    """ This view handles the request for displaying Modules with CsafMatches as a table. """
    queryset = Module.objects.annotate(
            new_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'module': OuterRef('pk')})
                    .filter(acceptance_status__in=[
                        models.CsafMatch.AcceptanceStatus.NEW,
                        models.CsafMatch.AcceptanceStatus.REOPENED])
                    .values('module')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'module': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
                    .values('module')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'module': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)
                    .values('module')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            total_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'module': OuterRef('pk')})
                    .values('module')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).filter(total_count__gt=0)
    table = tables.ModulesWithMatchTable


@register_model_view(Software, name='withmatches', path='withmatches', detail=False)
class SoftwareListWithCsafMatches(generic.ObjectListView):
    """ This view handles the request for displaying Software with CsafMatches as a table. """
    queryset = Software.objects.annotate(
            new_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(acceptance_status__in=[
                        models.CsafMatch.AcceptanceStatus.NEW,
                        models.CsafMatch.AcceptanceStatus.REOPENED])
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED)
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(acceptance_status=models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE)
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            total_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).filter(total_count__gt=0)
    table = tables.SoftwareWithMatchTable
