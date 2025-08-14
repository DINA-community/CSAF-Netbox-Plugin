from . import models, views
from django.urls import path
from netbox.views.generic import ObjectChangeLogView

urlpatterns = (
    path('csafdocument/', views.CsafDocumentListView.as_view(), name='csafdocument_list'),
    path('csafdocument/add/', views.CsafDocumentEditView.as_view(), name='csafdocument_add'),
    path('csafdocument/<int:pk>/', views.CsafDocumentView.as_view(), name='csafdocument'),
    #path('csafdocument/<int:pk>/devices/', views.DeviceListForCsafDocumentView.as_view(), name='deviceslistforcsafdocument'),
    path('csafdocument/<int:pk>/edit/', views.CsafDocumentEditView.as_view(), name='csafdocument_edit'),
    path('csafdocument/<int:pk>/delete/', views.CsafDocumentDeleteView.as_view(), name='csafdocument_delete'),
    path('csafdocument/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='csafdocument_changelog', kwargs={
        'model': models.CsafDocument
    }),
    
    path('device/<int:pk>/csafmatches/', views.CsafMatchListForDeviceView.as_view(), name='csafmatchlistfordevice'),
)
