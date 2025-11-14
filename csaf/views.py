from datetime import datetime
import logging
from django.conf import settings
import requests
from csaf.api.views import getFromJson
from dcim.models import Device
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, OuterRef, Subquery, QuerySet
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import View
from netbox.views import generic
from utilities.htmx import htmx_partial
from utilities.tables import get_table_configs
from utilities.views import ViewTab, register_model_view, GetReturnURLMixin
from . import forms, models, tables, filtersets
from d3c.models import Software


class Synchronisers(View):
    """
    Display the status of configured synchronisers.
    """
    def get(self, request):
        rawData = "data!"
        systems = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','urls'), [])
        try:
            startStr = request.GET.get('start', -1)
            startIdx = int(startStr)
            rawData += f' Starting {startIdx} '
            if startIdx >= 0 and startIdx < len(systems):
                system = systems[startIdx]
                token = getSyncToken(request, system)
                if token is not None:
                    startSystem(request, system, token)
                return redirect(request.path)
        except ValueError:
            messages.error(request, f"Not an int: {startStr}")
            

        data = []
        idx = 0;
        for system in systems:
            name = getFromJson(system, ('name',), 'Unnamed')
            token = getSyncToken(request, system)
            if token is None:
                systemData = {
                    'name': name,
                    'lastSync': '-',
                    'state': 'Login Failed',
                    'started': '-',
                    'index': idx,
                }
                data.append(systemData)
                idx += 1
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
                idx += 1
                continue
            rawData = rawData + ' \n ' + f"{status}";
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
            data.append(systemData)
            idx += 1

        return render(request, 'csaf/synchronisers.html', {
            'rawData': rawData,
            'data': data
        })


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
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to start {name}: {ex}")



def getStatus(request, system, token):
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','synchronisers','verify_ssl'), True)
    verifySsl = getFromJson(system, ('verify_ssl'), verifySsl)
    baseUrl = getFromJson(system, ('url',), None)
    name = getFromJson(system, ('name',), 'Unnamed')
    type = getFromJson(system, ('type',), 'normal')
    status_url = f"{baseUrl}/task/status"
    try:
        response = requests.get(
            status_url,
            headers={'Authorization': 'Bearer ' + token},
            verify=verifySsl,
        )
        if (response.status_code < 200 or response.status_code >= 300):
            messages.error(request, f"Failed to fetch status of {name}: {response.text}")
        return response.json()
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to fetch status of {name}: {ex}")


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

    baseUrl.removesuffix('/')
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
        return response.json().get('access_token')
    except requests.exceptions.RequestException as ex:
        messages.error(request, f"Failed to login to {name}: {ex}")


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

@register_model_view(models.CsafDocument, name='list', detail=False)
class CsafDocumentListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafDocuments as a table. """
    queryset = models.CsafDocument.objects.annotate(
        match_count=Coalesce(Subquery(
            models.CsafMatch.objects.filter(
                **{'csaf_document': OuterRef('pk')}
            ).filter(status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED]).values(
                'csaf_document'
            ).annotate(
                c=Count('*')
            ).values('c')), 0),
    )
    table = tables.CsafDocumentTable
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
    filtersets = filtersets.CsafDocumentFilterSet
    table = tables.CsafDocumentTable


@register_model_view(models.CsafMatch)
class CsafMatchView(generic.ObjectView):
    """ This view handles the request for displaying a CsafMatch. """
    queryset = models.CsafMatch.objects.all()


@register_model_view(models.CsafMatch, name='list', detail=False)
class CsafMatchListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafMatches as a table. """
    queryset = models.CsafMatch.objects.all()
    table = tables.CsafMatchTable
    actions = {
        'add': {'add'},
        'bulk_edit': {'change'},
        'bulk_delete': {'delete'},
    }


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
    queryset = models.CsafMatch.objects.all()
    filtersets = filtersets.CsafMatchFilterSet
    table = tables.CsafMatchTable


class CsafMatchListFor(generic.ObjectChildrenView, GetReturnURLMixin):
    child_model = models.CsafMatch
    base_template = 'generic/object_children.html'
    template_name = 'csaf/csafmatch_list.html'
    linkName = 'None'

    def get_children_for(self, parent):
        return self.child_model.objects

    def post(self, request, *args, **kwargs):
        logger = logging.getLogger('csaf.views.CsafMatchListFor')
        logger.debug("POST from Match List")
        instance = self.get_object(**kwargs)

        user = request.user
        if not user.has_perms(('csaf.edit_csafmatch',)):
            return self.handle_no_permission()

        targetStatus = request.POST.get('targetStatus', "")
        if targetStatus not in ['N', 'C', 'R', 'F']:
            messages.error(request, f"Unknown CSAF-Match status: {targetStatus}.")
            return self.get(request, args, kwargs)

        selected_objects = self.get_children_for(instance).filter(
            pk__in=request.POST.getlist('pk'),
        )
        with transaction.atomic():
            count = 0
            for csafMatch in selected_objects:
                csafMatch.status = targetStatus
                csafMatch.save()
                count += 1
        messages.success(request, f"Updated {count} CSAF-Matches")
        return redirect(self.get_return_url(request))


    def get(self, request, *args, **kwargs):
        """
        GET handler for rendering child objects.
        """
        instance = self.get_object(**kwargs)
        statusString, status, statusSearch = handleStatus(request)
        childObjects = self.get_children_for(instance).filter(status__in=statusSearch)

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
            'status': status,
            'statusString': statusString,
            'return_url': request.get_full_path(),
            **self.get_extra_context(request, instance),
        })


# CsafMatches view for one device
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
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(device=parent)


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
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(csaf_document=parent)



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
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count(),
        permission='csaf.view_csafmatch'
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(software=parent)


def handleStatus(request):
    statusString = request.GET.get('statusString', '1100')
    status = {
        'N': int(statusString[0]),
        'C': int(statusString[1]),
        'R': int(statusString[2]),
        'F': int(statusString[3]),
    }
    toggle = request.GET.get('toggle', "")
    if toggle in ['N', 'C', 'R', 'F']:
        status[toggle] = 1 - int(status[toggle])
    statusString = "" + str(status['N']) + str(status['C']) + str(status['R']) + str(status['F'])
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
                    .filter(status=models.CsafMatch.Status.NEW)
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .filter(status=models.CsafMatch.Status.CONFIRMED)
                    .values('device')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'device': OuterRef('pk')})
                    .filter(status__in=[models.CsafMatch.Status.FALSE_POSITIVE,models.CsafMatch.Status.RESOLVED])
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


@register_model_view(Software, name='withmatches', path='withmatches', detail=False)
class SoftwareListWithCsafMatches(generic.ObjectListView):
    """ This view handles the request for displaying Software with CsafMatches as a table. """
    queryset = Software.objects.annotate(
            new_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(status=models.CsafMatch.Status.NEW)
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            confirmed_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(status=models.CsafMatch.Status.CONFIRMED)
                    .values('software')
                    .annotate(c=Count('*'))
                    .values('c'))
        ).annotate(
            resolved_count=Subquery(
                models.CsafMatch.objects
                    .filter(**{'software': OuterRef('pk')})
                    .filter(status__in=[models.CsafMatch.Status.FALSE_POSITIVE,models.CsafMatch.Status.RESOLVED])
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

