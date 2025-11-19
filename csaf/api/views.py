"""
    These classes are needed for bulk update and delete operations.
"""
from .. import filtersets, models
from .serializers import CsafDocumentSerializer, CsafMatchSerializer
from core.choices import JobIntervalChoices
from datetime import timedelta
from django.conf import settings
from django.db import IntegrityError
import requests
from rq.utils import now
from netbox.api.viewsets import NetBoxModelViewSet
from netbox.jobs import JobRunner, system_job
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

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
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
            CsafDocSyncJob.enqueue(schedule_at = now() + timedelta(seconds=10))
            return serializer.data.get("id")
        except (ValidationError, IntegrityError) as ex:
            # Race condition, someone else just created the document
            query = models.CsafDocument.objects.filter(docurl = docurl)
            entity = query.get()

    return entity.id


def truncate(length, data):
    if data is None:
        return data
    if len(data) > length:
        print(f"truncated to {length}: {data}")
        return data[0:length]
    return data

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
        try:
            print(f"Requesting: {docurl}")
            result = requests.get(
                url=docurl,
                headers=headers
            )
            jsonDoc = result.json()
            code = getFromJson(jsonDoc, ('code',), 200)
            if code == 404:
                doc.title = TITLE_NOT_FOUND
            else:
                doc.lang = truncate(20, getFromJson(jsonDoc, ('document','lang'), None))
                doc.title = truncate(1000, getFromJson(jsonDoc, ('document','title'), 'No Title'))
                doc.version = truncate(50, getFromJson(jsonDoc, ('document','tracking', 'version'), None))
                doc.publisher = truncate(100, getFromJson(jsonDoc, ('document','publisher', 'name'), None))
            print(f"Loaded: {doc.title}")
            doc.save()
        except requests.exceptions.RequestException as ex:
            print("Failed to fetch document")
            print(ex)
            doc.title = TITLE_FAILED
            if not doc.version or int(doc.version) != doc.version:
                doc.version = 1
            else:
                doc.version = int(doc.version) + 1
            doc.save()
        except Exception as e:
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

        if current is not None:
            return current

        return dflt
    except Exception:
        return dflt

def getToken() -> str:
    """Retrieve an access token via Keycloak."""
    keycloakUrl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba','keycloak_url'), None)
    keycloakUrl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba_keycloak_url'), keycloakUrl)
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba','keycloak_verify_ssl'), True)
    verifySsl = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba_keycloak_verify_ssl'), verifySsl)
    username = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba','username'), None)
    username = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba_username'), username)
    password = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba','password'), None)
    password = getFromJson(settings.PLUGINS_CONFIG, ('csaf','isduba_password'), password)

    token_url = f"{keycloakUrl}/realms/isduba/protocol/openid-connect/token"
    try:
        print(f"Requesting: {token_url}")
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
        if (response.status_code < 200 or response.status_code >= 300):
            print(f"Failed to login: {response.content}")
        return response.json().get("access_token")
    except requests.exceptions.RequestException as ex:
        print("Failed to login to ISDuBA")
        print(ex)

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
            result = []
            for data in request.data:
                if isinstance(data.get('csaf_document'), str):
                    data['csaf_document'] = createDocumentForData({'docurl':data['csaf_document']})
                entity = createMatchForData(data)
                result.append(entity)
        else:
            data = request.data
            if isinstance(data.get('csaf_document'), str):
                data['csaf_document'] = createDocumentForData({'docurl':data['csaf_document']})
            result = createMatchForData(data)

        return Response(result, status = status.HTTP_201_CREATED)

def createMatchForData(data):
    csaf_document = data.get('csaf_document')
    device = data.get('device')
    software = data.get('software')
    product_name_id = data.get('product_name_id')
    query = models.CsafMatch.objects.filter(csaf_document = csaf_document, device=device, software=software, product_name_id=product_name_id)
    try:
        entity = query.get()
        score = data.get('score', 0)
        description = data.get('description', '')
        if entity.score < score:
            if entity.description is None:
                entity.description = ''
            entity.description += '\n'
            entity.description += description
            entity.description += f'\nScore increased from {entity.score} to {score}'
            entity.score = score
            if entity.status == models.CsafMatch.Status.FALSE_POSITIVE:
                entity.status = models.CsafMatch.Status.REOPENED
                entity.description += f'\nReopened'
            entity.save()
    except models.CsafMatch.DoesNotExist:
        serializer = CsafMatchSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return serializer.data
        except (ValidationError, IntegrityError) as ex:
            # Race condition, someone else just created the match
            query = models.CsafMatch.objects.filter(csaf_document = csaf_document, device=device, software=software, product_name_id=product_name_id)
            entity = query.get()

    return CsafMatchSerializer(entity).data
