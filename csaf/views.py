from dcim.models import Device
from django.db.models import Count, OuterRef, Subquery, QuerySet
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from netbox.views import generic
from utilities.htmx import htmx_partial
from utilities.tables import get_table_configs
from utilities.views import ViewTab, register_model_view
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


# CsafMatches view for one device
@register_model_view(Device, name='csafmatchlistfordeviceview', path='csafmatches', )
class CsafMatchListForDeviceView(generic.ObjectChildrenView):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    queryset = Device.objects.all()
    child_model = models.CsafMatch
    table = tables.CsafMatchListForDeviceTable
    base_template = 'generic/object_children.html'
    template_name = 'csaf/csafmatch_list.html'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            device=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get(self, request, *args, **kwargs):
        """
        GET handler for rendering child objects.
        """
        instance = self.get_object(**kwargs)
 
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
        search={0}
        for s,v in status.items():
            if v:
                search.add(s)

        child_objects = self.child_model.objects.filter(device=instance).filter(status__in=search)

        if self.filterset:
            child_objects = self.filterset(request.GET, child_objects, request=request).qs

        # Determine the available actions
        actions = self.get_permitted_actions(request.user, model=self.child_model)
        has_bulk_actions = any([a.startswith('bulk_') for a in actions])

        table_data = self.prep_table_data(request, child_objects, instance)
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


@register_model_view(model=models.CsafDocument, name='matchlistforcsafdocument', path='csafmatches', )
class CsafMatchListForCsafDocumentView(generic.ObjectChildrenView):
    queryset = models.CsafDocument.objects.all()
    child_model = models.CsafMatch
    table = tables.CsafMatchListForCsafDocumentTable
    base_template = 'generic/object_children.html'
    template_name = 'csaf/csafmatch_list.html'

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            csaf_document=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get(self, request, *args, **kwargs):
        """
        GET handler for rendering child objects.
        """
        instance = self.get_object(**kwargs)
 
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
        search={0}
        for s,v in status.items():
            if v:
                search.add(s)

        child_objects = self.child_model.objects.filter(csaf_document=instance).filter(status__in=search)

        if self.filterset:
            child_objects = self.filterset(request.GET, child_objects, request=request).qs

        # Determine the available actions
        actions = self.get_permitted_actions(request.user, model=self.child_model)
        has_bulk_actions = any([a.startswith('bulk_') for a in actions])

        table_data = self.prep_table_data(request, child_objects, instance)
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


@register_model_view(model=Software, name='matchlistforsoftware', path='csafmatches', )
class CsafMatchListForSoftwareView(generic.ObjectChildrenView):
    queryset = Software.objects.all()
    child_model = models.CsafMatch
    table = tables.CsafMatchListForSoftwareTable
    template_name = 'generic/object_children.html'
    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            software=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get_children(self, request, parent):
        return self.child_model.objects.filter(software=parent)


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

