from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('stream/', views.stream_logs, name='stream_logs'),
    path('export/excel/', views.export_excel, name='export_excel'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
]