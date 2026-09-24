from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views, scan_views

app_name = "reports"

router = DefaultRouter()
router.register("disease-reports", views.DiseaseReportViewSet, basename="disease-report")
router.register("pest-reports", views.PestReportViewSet, basename="pest-report")
router.register("expert-reviews", views.ExpertReviewViewSet, basename="expert-review")

urlpatterns = [
    path("api/", include(router.urls)),
    # Public (no login required)
    path("scan/", scan_views.scan_page, name="scan_page"),
    path("scan/analyse/", scan_views.analyse_image, name="scan_analyse"),
    # Farmer authenticated views
    path("farmer/upload/", views.upload_report, name="upload_report"),
    path("farmer/reports/", views.report_list, name="report_list"),
    path("farmer/reports/<int:pk>/", views.report_detail, name="report_detail"),
    path("farmer/farms/<int:farm_id>/crop-cycles/", views.crop_cycles_for_farm, name="crop_cycles_for_farm"),
]
