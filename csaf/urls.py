from . import models, views
from django.urls import include, path
from netbox.views.generic import ObjectChangeLogView
from utilities.urls import get_model_urls

urlpatterns = (
    path('csafdocument/', include(get_model_urls('csaf', 'csafdocument', detail=False))),
    path('csafdocument/<int:pk>/', include(get_model_urls('csaf', 'csafdocument'))),

    path('csafmatch/', include(get_model_urls('csaf', 'csafmatch', detail=False))),
    path('csafmatch/<int:pk>/', include(get_model_urls('csaf', 'csafmatch'))),

)
