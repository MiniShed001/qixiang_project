from django.urls import path
from . import views

app_name = 'meteo'

urlpatterns = [
    path('', views.index, name='index'),
    path('surface/', views.surface, name='surface'),
    path('upperair/', views.upperair, name='upperair'),
    path('ocean/', views.ocean, name='ocean'),
    path('radar/', views.radar, name='radar'),
    path('satellite/', views.satellite, name='satellite'),
]
