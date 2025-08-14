from dcim.models import Device
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from . import forms, models, tables


@register_model_view(models.CsafDocument, 'edit')
class CsafDocumentEditView(generic.ObjectEditView):
    """ This view handles the edit requests for the CsafDocument model. """
    queryset = models.CsafDocument.objects.all()
    form = forms.CsafDocumentForm


class CsafDocumentDeleteView(generic.ObjectDeleteView):
    """ This view handles the delete requests for the CsafDocument model. """
    queryset = models.CsafDocument.objects.all()


class CsafDocumentView(generic.ObjectView):
    """ This view handles the request for displaying a CsafDocument. """
    queryset = models.CsafDocument.objects.all()


class CsafDocumentListView(generic.ObjectListView):
    """ This view handles the request for displaying multiple CsafDocuments as a table. """
    queryset = models.CsafDocument.objects.all()
    table = tables.CsafDocumentTable

# CsafMatches view for one device
@register_model_view(Device, name='csafmatchlistfordeviceview', path='csafmatches')
class CsafMatchListForDeviceView(View):
    """ Handles the request of displaying multiple Csaf Matches associated to a Device. """
    base_template = 'dcim/device.html'
    template_name = 'csaf/csafmatches_for_device.html'
    table = tables.CsafMatchListForDeviceTable

    tab = ViewTab(
        label='CSAF Matches',
        badge=lambda obj: models.CsafMatch.objects.filter(device=obj, status=('NEW',"Confirmed")).count()
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
