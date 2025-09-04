import logging
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


@register_model_view(models.CsafDocument)
class CsafDocumentView(generic.ObjectView):
    """ This view handles the request for displaying a CsafDocument. """
    queryset = models.CsafDocument.objects.all()


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


@register_model_view(models.CsafMatch)
class CsafMatchView(generic.ObjectView):
    """ This view handles the request for displaying a CsafMatch. """
    queryset = models.CsafMatch.objects.all()


@register_model_view(models.CsafMatch, name='list', detail=False)
class CsafMatchListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafMatches as a table. """
    queryset = models.CsafMatch.objects.all()
    table = tables.CsafMatchTable


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
    queryset = Device.objects.all()
    table = tables.CsafMatchListForDeviceTable
    linkName= 'device'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            device=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(device=parent)


@register_model_view(model=models.CsafDocument, name='matchlistforcsafdocument', path='csafmatches', )
class CsafMatchListForCsafDocumentView(CsafMatchListFor):
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafMatchListForCsafDocumentTable
    linkName= 'document'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            csaf_document=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get_children_for(self, parent):
        return self.child_model.objects.filter(csaf_document=parent)



@register_model_view(model=Software, name='matchlistforsoftware', path='csafmatches', )
class CsafMatchListForSoftwareView(CsafMatchListFor):
    queryset = Software.objects.all()
    table = tables.CsafMatchListForSoftwareTable
    linkName= 'software'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            software=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
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

