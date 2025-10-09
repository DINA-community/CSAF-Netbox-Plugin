"""
    These classes are needed for bulk update and delete operations.
"""
from netbox.api.viewsets import NetBoxModelViewSet
from .. import filtersets, models
from .serializers import CsafDocumentSerializer, CsafMatchSerializer

from django.db.models import Count
from rest_framework.response import Response

class CsafDocumentViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafDocument.
    """
    queryset = models.CsafDocument.objects.all()
    serializer_class = CsafDocumentSerializer
    filterset_class = filtersets.CsafDocumentFilterSet


class CsafDocumentForUrlView(NetBoxModelViewSet):
    """ This view expects a json object: 
      {
        "docurl": "<url of the document>",
        "title": "Optional  title of the document",
        "version": "Optional version",
        "lang": "Opional language",
        "publisher": "Opional publisher"
      }
      If there is currently NO document with the given URL, a new document is created using all fields present.
      If there is already a document with the given URL, nothing is done.
      The id of the document is returned:
      {
        "id": <DocumentId>
      }
    """
    queryset = models.CsafDocument.objects.all()
    serializer_class = CsafDocumentSerializer

    def create(self, request, *args, **kwargs):
        data = request.data
        docurl = data.get('docurl')
        if not docurl:
            return Response("Missing docurl", status=404)

        query = models.CsafDocument.objects.filter(docurl = docurl)
        try:
            entity = query.get()
        except models.CsafDocument.DoesNotExist:
            if "title" not in data:
                data["title"] = docurl
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            data = {
                "id": serializer.data.get("id")
            }
            return Response(data, status=201, headers=headers)

        data = {
            "id": entity.id
        }
        return Response(data, status=400)



class CsafMatchViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafMatch.
    """
    queryset = models.CsafMatch.objects.all()
    serializer_class = CsafMatchSerializer
    filterset_class = filtersets.CsafMatchFilterSet
