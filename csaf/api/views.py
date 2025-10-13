"""
    These classes are needed for bulk update and delete operations.
"""
from .. import filtersets, models
from .serializers import CsafDocumentSerializer, CsafMatchSerializer
from core.choices import JobIntervalChoices
from datetime import datetime, timedelta
from django.conf import settings
from django.db.models import Count
import requests
from rq.utils import now
from netbox.api.viewsets import NetBoxModelViewSet
from netbox.jobs import JobRunner, system_job
from rest_framework.response import Response
from rest_framework import status


TITLE_LOADING = "Loading..."
TITLE_FAILED = "Loading Failed."
TITLE_NOT_FOUND = "No Document Found"


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
            return Response("Missing docurl", status = status.HTTP_404_NOT_FOUND)

        docId = createDocumentForData(data)
        result = {
            "id": docId
        }
        return Response(result, status = status.HTTP_200_OK)


def createDocumentForData(data):
    docurl = data.get('docurl')
    query = models.CsafDocument.objects.filter(docurl = docurl)
    try:
        entity = query.get()
    except models.CsafDocument.DoesNotExist:
        if "title" not in data:
            data["title"] = TITLE_LOADING
        serializer = CsafDocumentSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        CsafDocSyncJob.enqueue(schedule_at = now() + timedelta(seconds=10))
        return serializer.data.get("id")

    return entity.id


def fetchLoadingDocuments():
    query = models.CsafDocument.objects.filter(title = TITLE_LOADING)
    token = False
    for doc in query:
        docurl = doc.docurl
        if not token:
            token = getToken()
        headers = {
            'authorization': 'Bearer ' + token
        }
        result = requests.get(
            url=docurl,
            headers=headers
        )
        try:
            jsonDoc = result.json()
            code = getFromJson(jsonDoc, ('code',), 200)
            if code == 404:
                doc.title = TITLE_NOT_FOUND
            else:
                doc.lang = getFromJson(jsonDoc, ('document','lang'), None)
                doc.title = getFromJson(jsonDoc, ('document','title'), 'No Title')
                doc.version = getFromJson(jsonDoc, ('document','tracking', 'version'), None)
                doc.publisher = getFromJson(jsonDoc, ('document','publisher', 'name'), None)
            print(f"Loaded: {doc.title}")
            doc.save()
        except requests.exceptions.JSONDecodeError as e:
            print(e)
            doc.title = TITLE_FAILED
            if not doc.version or int(doc.version) != doc.version:
                doc.version = 1
            else:
                doc.version = int(doc.version) + 1
            doc.save()


def getFromJson(document, path, dflt):
    current = document
    try:
        for p in path:
            current = current.get(p)
        return current
    except Exception:
        return dflt

def getToken() -> str:
    """Retrieve an access token via Keycloak."""
    keycloakUrl = settings.PLUGINS_CONFIG['csaf']['isduba_keycloak_url']
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba_keycloak_verify_ssl'), True)
    username = settings.PLUGINS_CONFIG['csaf']['isduba_username']
    password = settings.PLUGINS_CONFIG['csaf']['isduba_password']

    token_url = f"{keycloakUrl}/realms/isduba/protocol/openid-connect/token"
    response = requests.post(
        token_url,
        data={
            "grant_type": "password",
            "client_id": "auth",
            "username": username,
            "password": password,
        },
        verify=verifySsl,
    )
    return response.json().get("access_token")


@system_job(interval=JobIntervalChoices.INTERVAL_HOURLY)
class CsafDocSyncJob(JobRunner):
    class Meta:
        name = "CSAF Document Sync"

    def run(self, *args, **kwargs):
        fetchLoadingDocuments()


class CsafMatchViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafMatch.
    """
    queryset = models.CsafMatch.objects.all()
    serializer_class = CsafMatchSerializer
    filterset_class = filtersets.CsafMatchFilterSet

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, list):
            for data in request.data:
                if isinstance(data.get('csaf_document'), str):
                    data['csaf_document'] = createDocumentForData({'docurl':data['csaf_document']})
        else:
            if isinstance(request.data.get('csaf_document'), str):
                request.data['csaf_document'] = createDocumentForData({'docurl':request.data['csaf_document']})

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
