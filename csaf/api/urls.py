from netbox.api.routers import NetBoxRouter
from . import views

app_name = 'csaf-api'

router = NetBoxRouter()
router.register('csafdocument-list', views.CsafDocumentViewSet)
router.register('csafdocforurl', views.CsafDocumentForUrlView, basename = "docforurl")
router.register('csafmatch-list', views.CsafMatchViewSet)
router.register('csafvulnerability-list', views.CsafVulnerabilityViewSet)

urlpatterns = router.urls
