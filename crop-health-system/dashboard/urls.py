from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.officer_dashboard, name="index"),
    path("api/hotspots.geojson", views.hotspot_geojson, name="hotspot_geojson"),
]
