from netbox.api.routers import NetBoxRouter
from . import views

app_name = 'csaf-api'

router = NetBoxRouter()
router.register('csafdocument-list', views.CsafDocumentViewSet)
router.register('csafmatch-list', views.CsafMatchViewSet)

urlpatterns = router.urls

