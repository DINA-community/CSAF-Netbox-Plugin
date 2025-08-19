from . import models, views
from django.urls import path
from netbox.views.generic import ObjectChangeLogView

urlpatterns = (
    path('csafdocument/', views.CsafDocumentListView.as_view(), name='csafdocument_list'),
    path('csafdocument/add/', views.CsafDocumentEditView.as_view(), name='csafdocument_add'),
    path('csafdocument/<int:pk>/', views.CsafDocumentView.as_view(), name='csafdocument'),
    path('csafdocument/<int:pk>/csafmatches/', views.CsafMatchListForCsafDocumentView.as_view(), name='csafdocument_matchlistforcsafdocument'),
    path('csafdocument/<int:pk>/edit/', views.CsafDocumentEditView.as_view(), name='csafdocument_edit'),
    path('csafdocument/<int:pk>/delete/', views.CsafDocumentDeleteView.as_view(), name='csafdocument_delete'),
    path('csafdocument/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='csafdocument_changelog', kwargs={
        'model': models.CsafDocument
    }),
    
    path('csafmatch/', views.CsafMatchListView.as_view(), name='csafmatch_list'),
    path('csafmatch/add/', views.CsafMatchEditView.as_view(), name='csafmatch_add'),
    path('csafmatch/<int:pk>/', views.CsafMatchView.as_view(), name='csafmatch'),
    path('csafmatch/<int:pk>/edit/', views.CsafMatchEditView.as_view(), name='csafmatch_edit'),
    path('csafmatch/<int:pk>/delete/', views.CsafMatchDeleteView.as_view(), name='csafmatch_delete'),
    path('csafmatch/<int:pk>/changelog/', ObjectChangeLogView.as_view(), name='csafmatch_changelog', kwargs={
        'model': models.CsafMatch
    }),

    path('device/<int:pk>/csafmatches/', views.CsafMatchListForDeviceView.as_view(), name='csafmatchlistfordevice'),

    path('software/<int:pk>/csafmatches/', views.CsafMatchListForSoftwareView.as_view(), name='software_csafmatchlistforsoftware'),
)
