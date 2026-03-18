from datetime import datetime
import logging
from django.conf import settings
import requests
import time
from csaf.api.views import getFromJson
from dcim.models import Device, DeviceType, Module
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, QuerySet
from django.db.models.functions import Coalesce
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
                'started': started,
                'index': idx,
            }
            isMatcher = getFromJson(system, ('isMatcher',), False)
            if isMatcher:
                systemData['clear'] = CLEAR_TABLE
                systemData['info'] = buildInfoStringMatcher(system, status)
                systemData['running'] = status['running']
            elif 'total_products_fetched' in status:
                systemData['info'] = buildInfoStringCsafSync(system, status)
            if request.user.has_perm(RIGHT_SYNC_START):
                systemData['canStart'] = True
            if request.user.has_perm(RIGHT_SYNC_STOP):
                systemData['canStop'] = True
            if request.user.has_perm(RIGHT_SYNC_CLEAR):
                systemData['canClear'] = True
            data.append(systemData)

        return render(request, 'csaf/synchronisers.html', {
            'data': data,
            'error_help': error_help,
        })

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
    trigger = request.GET.get('trigger', None)
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
    device = request.GET.get('device', -1)
    module = request.GET.get('module', -1)
    software = request.GET.get('software', -1)

    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    startUrl = f"{baseUrl}/task/start"
    try:
        assets = []
        csaf_documents = []
        addUrlForDocument(csaf_documents, request.GET.get('document', None))
        addUrlForDevice(assets, request.GET.get('device', None), system)
        addUrlForModule(assets, request.GET.get('module', None), system)
        addUrlForDeviceType(assets, request.GET.get('deviceType', None), system)
        addUrlForSoftware(assets, request.GET.get('software', None), system)
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
        startStr = request.GET.get('start', -1)
        startIdx = int(startStr)
        if startIdx >= 0 and startIdx < len(systems):
            if not request.user.has_perm(RIGHT_SYNC_START):
                messages.error(request, f'User does not have permission {RIGHT_SYNC_START}')
                return

            system = systems[startIdx]
            (token, msg) = getSyncToken(request, system)
            if token is not None:
                startSystem(request, system, token)
            return redirect(request.path)
    except ValueError:
        messages.error(request, f"Not an int: {startStr}")


def startSystem(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    startUrl = f"{baseUrl}/task/start"
    try:
        response = requests.post(
            startUrl,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
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
        stopStr = request.GET.get('stop', -1)
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
        taskIdStr = request.GET.get('task_id', -1)
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
        clearStr = request.GET.get('clear', None)
        if clearStr is None:
            return False
        if not request.user.has_perm(RIGHT_SYNC_CLEAR):
            messages.error(request, f'User does not have permission {RIGHT_SYNC_CLEAR}')
            return
        if not clearStr in CLEAR_TABLE:
            messages.error(request, f"Unknown clear command: {clearStr}")
            return False
        idxStr = request.GET.get('idx', -1)
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
        return result
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch running tasks of {name}: {ex}")


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

        vulnerability_id = request.POST.get('vulnerability_id')
        remediation_status = request.POST.get('targetRemStatus')
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

        instance.set_vulnerability_remediation(vulnerability, remediation_status)
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


# CsafMatches view for all Matches
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
    def get(self, request, *args, **kwargs):
        statusString, acceptance_status, statusSearch = handleStatus(request)
        if self.filterset:
            self.queryset = self.filterset(request.GET, self.queryset, request=request).qs
        childObjects = self.queryset.filter(acceptance_status__in=statusSearch)

        # Determine the available actions
        actions = self.get_permitted_actions(request.user, model=self.model)
        has_bulk_actions = any([a.startswith('bulk_') for a in actions])

        table = self.get_table(childObjects, request, has_bulk_actions)

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
            'statusFilter': True,
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

        targetAccStatus = request.POST.get('targetAccStatus', "")
        if targetAccStatus:
            if targetAccStatus not in models.CsafMatch.AcceptanceStatus:
                messages.error(request, f"Unknown CSAF-Match AcceptanceStatus: {targetAccStatus}.")
                return self.get(request, args, kwargs)

            selected_objects = self.queryset.filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                for csafMatch in selected_objects:
                    csafMatch.acceptance_status = targetAccStatus
                    csafMatch.save()
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")

        targetRemStatus = request.POST.get('targetRemStatus', "")
        if targetRemStatus:
            if targetRemStatus not in models.CsafMatch.RemediationStatus:
                messages.error(request, f"Unknown CSAF-Match RemediationStatus: {targetRemStatus}.")
                return self.get(request, args, kwargs)

            selected_objects = self.queryset.filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                for csafMatch in selected_objects:
                    csafMatch.set_all_vulnerability_remediations(targetRemStatus)
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")
        return redirect(self.get_return_url(request))


class CsafMatchListFor(generic.ObjectChildrenView, GetReturnURLMixin):
    child_model = models.CsafMatch
    filterset = filtersets.CsafMatchFilterSet
    base_template = 'generic/object_children.html'
    template_name = 'csaf/csafmatch_list.html'
    linkName = 'None'

    def get_children_for(self, parent):
        return self.child_model.objects.select_related(
            'device',
            'module',
            'software',
            'csaf_document',
        ).prefetch_related('csaf_document__vulnerabilities', 'vulnerability_statuses')

    def post(self, request, *args, **kwargs):
        logger = logging.getLogger('csaf.views.CsafMatchListFor')
        logger.debug("POST from Match List")
        instance = self.get_object(**kwargs)

        user = request.user
        if not user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        targetAccStatus = request.POST.get('targetAccStatus', "")
        if targetAccStatus:
            if targetAccStatus not in models.CsafMatch.AcceptanceStatus:
                messages.error(request, f"Unknown CSAF-Match AcceptanceStatus: {targetAccStatus}.")
                return redirect(self.get_return_url(request))

            selected_objects = self.get_children_for(instance).filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                for csafMatch in selected_objects:
                    csafMatch.acceptance_status = targetAccStatus
                    csafMatch.save()
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")

        targetRemStatus = request.POST.get('targetRemStatus', "")
        if targetRemStatus:
            if targetRemStatus not in models.CsafMatch.RemediationStatus:
                messages.error(request, f"Unknown CSAF-Match RemediationStatus: {targetRemStatus}.")
                return redirect(self.get_return_url(request))

            selected_objects = self.get_children_for(instance).filter(
                pk__in=request.POST.getlist('pk'),
            )
            with transaction.atomic():
                count = 0
                for csafMatch in selected_objects:
                    csafMatch.set_all_vulnerability_remediations(targetRemStatus)
                    count += 1
            messages.success(request, f"Updated {count} CSAF-Matches")
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
        if not (part.startswith('statusString') or part.startswith('toggle')):
            result = result + part + '&'
    return result


    


# New CsafMatches view for one Device
@register_model_view(Device, name='newcsafmatchlistfordeviceview', path='csafmatchesnew', )
class CsafNewMatchListForDeviceView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Device.objects.all()
    table = tables.CsafMatchListForDeviceTable
    linkName= 'device'

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
class CsafMatchListForDeviceView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Device.objects.all()
    table = tables.CsafMatchListForDeviceTable
    linkName= 'device'

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

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            module=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.CONFIRMED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(
                module=parent
            ).filter(
                acceptance_status=models.CsafMatch.AcceptanceStatus.CONFIRMED
            )


# CsafMatches view for one Document
@register_model_view(model=models.CsafDocument, name='matchlistforcsafdocument', path='csafmatches', )
class CsafMatchListForCsafDocumentView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a CsafDocument. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafMatchListForCsafDocumentTable
    linkName= 'document'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            csaf_document=obj,
            acceptance_status__in=[
                models.CsafMatch.AcceptanceStatus.NEW,
                models.CsafMatch.AcceptanceStatus.CONFIRMED,
                models.CsafMatch.AcceptanceStatus.REOPENED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(csaf_document=parent)



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


# CsafMatches view for one Software
@register_model_view(model=Software, name='matchlistforsoftware', path='csafmatches', )
class CsafMatchListForSoftwareView(CsafMatchListFor):
    """ Handles the request of displaying multiple Csaf Matches associated to a Software Entity. """
    additional_permissions=('csaf.view_csafmatch',)
    queryset = Software.objects.all()
    table = tables.CsafMatchListForSoftwareTable
    linkName= 'software'

    tab = ViewTab(
        label='CSAF Matches',
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
