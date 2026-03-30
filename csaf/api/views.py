"""
    These classes are needed for bulk update and delete operations.
"""
from .. import filtersets, models
from .serializers import CsafDocumentSerializer, CsafMatchSerializer, CsafVulnerabilitySerializer
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
        "tracking_id": "Optional tracking id",
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
    verify_ssl = getDocumentVerifySsl()
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
                headers=headers,
                verify=verify_ssl,
            )
            jsonDoc = result.json()
            code = getFromJson(jsonDoc, ('code',), 200)
            if code == 404:
                doc.title = TITLE_NOT_FOUND
                doc.tracking_id = None
                doc.product_tree = None
                models.CsafVulnerability.objects.filter(csaf_document=doc).delete()
            else:
                doc.lang = truncate(20, getFromJson(jsonDoc, ('document','lang'), None))
                doc.title = truncate(1000, getFromJson(jsonDoc, ('document','title'), 'No Title'))
                doc.tracking_id = truncate(255, getFromJson(jsonDoc, ('document', 'tracking', 'id'), None))
                doc.version = truncate(50, getFromJson(jsonDoc, ('document','tracking', 'version'), None))
                doc.publisher = truncate(100, getFromJson(jsonDoc, ('document','publisher', 'name'), None))
                product_tree = getFromJson(jsonDoc, ('product_tree',), None)
                if product_tree is None:
                    product_tree = getFromJson(jsonDoc, ('document', 'product_tree'), None)
                doc.product_tree = product_tree
                syncVulnerabilitiesForDocument(doc, jsonDoc)
            print(f"Loaded: {doc.title}")
            doc.save()
        except requests.exceptions.RequestException as ex:
            print("Failed to fetch document")
            print(ex)
            doc.title = TITLE_FAILED
            doc.product_tree = None
            models.CsafVulnerability.objects.filter(csaf_document=doc).delete()
            if not doc.version or int(doc.version) != doc.version:
                doc.version = 1
            else:
                doc.version = int(doc.version) + 1
            doc.save()
        except Exception as e:
            print(e)
            doc.title = TITLE_FAILED
            doc.product_tree = None
            models.CsafVulnerability.objects.filter(csaf_document=doc).delete()
            if not doc.version or int(doc.version) != doc.version:
                doc.version = 1
            else:
                doc.version = int(doc.version) + 1
            doc.save()


def getBaseScore(vulnerability):
    scores = getFromJson(vulnerability, ('scores',), [])
    if not isinstance(scores, list):
        return None

    best = None
    for score in scores:
        base_score = getFromJson(score, ('cvss_v3', 'baseScore'), None)
        try:
            base_score = float(base_score)
        except (TypeError, ValueError):
            continue
        if best is None or base_score > best:
            best = base_score
    return best


def getSummary(vulnerability):
    notes = getFromJson(vulnerability, ('notes',), [])
    if not isinstance(notes, list):
        return None

    for note in notes:
        text = getFromJson(note, ('text',), None)
        if text:
            return truncate(10000, text)
    return None


def collectProductIds(data):
    """
    Recursively collect product IDs from CSAF structures.
    """
    values = set()
    if isinstance(data, str):
        value = data.strip()
        if value:
            values.add(value)
    elif isinstance(data, list):
        for item in data:
            values.update(collectProductIds(item))
    elif isinstance(data, dict):
        for item in data.values():
            values.update(collectProductIds(item))
    return values


def getProductIds(vulnerability):
    product_ids = set()

    # CSAF vulnerability-to-product mapping is encoded in product_status.
    product_status = getFromJson(vulnerability, ('product_status',), {})
    if isinstance(product_status, dict):
        for ids in product_status.values():
            product_ids.update(collectProductIds(ids))

    # Some producers add a direct list on the vulnerability itself.
    product_ids.update(collectProductIds(getFromJson(vulnerability, ('product_ids',), [])))

    # Some producers embed product references in remediations/threats/flags.
    for remediation in getFromJson(vulnerability, ('remediations',), []):
        if isinstance(remediation, dict):
            product_ids.update(collectProductIds(remediation.get('product_ids', [])))
    for threat in getFromJson(vulnerability, ('threats',), []):
        if isinstance(threat, dict):
            product_ids.update(collectProductIds(threat.get('product_ids', [])))
    for flag in getFromJson(vulnerability, ('flags',), []):
        if isinstance(flag, dict):
            product_ids.update(collectProductIds(flag.get('product_ids', [])))

    return sorted(product_ids)


def syncVulnerabilitiesForDocument(doc, jsonDoc):
    vulnerabilities = getFromJson(jsonDoc, ('vulnerabilities',), [])
    if not isinstance(vulnerabilities, list):
        vulnerabilities = []

    kept_ordinals = []
    for index, vulnerability in enumerate(vulnerabilities):
        ordinal = index + 1
        vulnerability_id = getFromJson(vulnerability, ('cve',), None)
        vulnerability_id = vulnerability_id or getFromJson(vulnerability, ('id',), None)
        vulnerability_id = vulnerability_id or f'vuln-{ordinal}'

        data = {
            'vulnerability_id': truncate(255, str(vulnerability_id)),
            'cve': truncate(100, getFromJson(vulnerability, ('cve',), None)),
            'title': truncate(1000, getFromJson(vulnerability, ('title',), None)),
            'summary': getSummary(vulnerability),
            'cwe': truncate(255, getFromJson(vulnerability, ('cwe', 'id'), None)),
            'cvss_base_score': getBaseScore(vulnerability),
            'product_ids': getProductIds(vulnerability),
        }
        models.CsafVulnerability.objects.update_or_create(
            csaf_document=doc,
            ordinal=ordinal,
            defaults=data,
        )
        kept_ordinals.append(ordinal)

    models.CsafVulnerability.objects.filter(csaf_document=doc).exclude(ordinal__in=kept_ordinals).delete()
    for match in models.CsafMatch.objects.filter(csaf_document=doc):
        match.sync_vulnerability_remediations()


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

def getDocumentVerifySsl():
    verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba', 'document_verify_ssl'), None)
    verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba_document_verify_ssl'), verify_ssl)
    if verify_ssl is None:
        verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba', 'verify_ssl'), True)
        verify_ssl = getFromJson(settings.PLUGINS_CONFIG, ('csaf', 'isduba_verify_ssl'), verify_ssl)
    return verify_ssl

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
            count = len(request.data)
            print(f"Handling {count} matches")
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
    module = data.get('module')
    software = data.get('software')
    product_name_id = data.get('product_name_id')
    query = models.CsafMatch.objects.filter(csaf_document = csaf_document, device=device, module=module, software=software, product_name_id=product_name_id)
    try:
        entity = query.get()
        print(f"Duplicate: {device}, {module}, {software}, {csaf_document}, {product_name_id}")
        score = data.get('score', 0)
        description = data.get('description', '')
        if entity.score < score:
            if entity.description is None:
                entity.description = ''
            entity.description += '\n'
            entity.description += description
            entity.description += f'\nScore increased from {entity.score} to {score}'
            entity.score = score
            if entity.acceptance_status == models.CsafMatch.AcceptanceStatus.FALSE_POSITIVE:
                entity.acceptance_status = models.CsafMatch.AcceptanceStatus.REOPENED
                entity.description += f'\nReopened'
            entity.save()
    except models.CsafMatch.DoesNotExist:
        print(f"New: {device}, {module}, {software}, {csaf_document}, {product_name_id}")
        serializer = CsafMatchSerializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return serializer.data.get('id')
        except (ValidationError, IntegrityError) as ex:
            print(f"Race: {device}, {module}, {software}, {csaf_document}, {product_name_id}")
            # Race condition, someone else just created the match
            query = models.CsafMatch.objects.filter(csaf_document = csaf_document, device=device, module=module, software=software, product_name_id=product_name_id)
            entity = query.get()

    entity.sync_vulnerability_remediations()
    return CsafMatchSerializer(entity).data.get('id')


class CsafVulnerabilityViewSet(NetBoxModelViewSet):
    """
    ViewSet for CsafVulnerability.
    """
    queryset = models.CsafVulnerability.objects.all()
    serializer_class = CsafVulnerabilitySerializer
    filterset_class = filtersets.CsafVulnerabilityFilterSet
