from dcim.models import Device
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from . import forms, models, tables
from d3c.models import Software


@register_model_view(models.CsafDocument)
class CsafDocumentView(generic.ObjectView):
    """ This view handles the request for displaying a CsafDocument. """
    queryset = models.CsafDocument.objects.all()


@register_model_view(models.CsafDocument, name='list', detail=False)
class CsafDocumentListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafDocuments as a table. """
    queryset = models.CsafDocument.objects.all()
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
class CsafMatchListForDeviceView(View):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    base_template = 'dcim/device.html'
    template_name = 'csaf/csafmatches_for_device.html'
    table = tables.CsafMatchListForDeviceTable

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            device=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get(self, request, **kwargs):
        obj = get_object_or_404(Device, **kwargs)
        matches = models.CsafMatch.objects.filter(device=self.kwargs["pk"])
        matches_table = tables.CsafMatchListForDeviceTable(matches)
        return render(request, self.template_name, {
            'object': obj,
            'table': matches_table,
            'base_template': self.base_template,
            'tab': self.tab,
        })


@register_model_view(model=models.CsafDocument, name='matchlistforcsafdocument', path='csafmatches', )
class CsafMatchListForCsafDocumentView(generic.ObjectChildrenView):
    queryset = models.CsafDocument.objects.all()
    child_model = models.CsafMatch
    table = tables.CsafMatchListForCsafDocumentTable
    template_name = 'generic/object_children.html'
    # filterset = filtersets.ConsolePortFilterSet
    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            csaf_document=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get_children(self, request, parent):
        return self.child_model.objects.filter(csaf_document=parent)


@register_model_view(model=Software, name='matchlistforsoftware', path='csafmatches', )
class CsafMatchListForSoftwareView(generic.ObjectChildrenView):
    queryset = Software.objects.all()
    child_model = models.CsafMatch
    table = tables.CsafMatchListForSoftwareTable
    template_name = 'generic/object_children.html'
    # filterset = filtersets.ConsolePortFilterSet
    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(
            software=obj,
            status__in=[models.CsafMatch.Status.NEW,models.CsafMatch.Status.CONFIRMED])
            .count()
    )

    def get_children(self, request, parent):
        return self.child_model.objects.filter(software=parent)

