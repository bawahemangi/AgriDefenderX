from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import permissions, viewsets

from farms.models import CropCycle, Farm

from .models import DiseaseReport, ExpertReview, PestReport
from .serializers import (
    DiseaseReportCreateSerializer,
    DiseaseReportSerializer,
    ExpertReviewSerializer,
    PestReportSerializer,
)
from .services import process_disease_report

# ---------------------------------------------------------------------------
# DRF API (for a future mobile app / external integrations)
# ---------------------------------------------------------------------------


class DiseaseReportViewSet(viewsets.ModelViewSet):
    queryset = DiseaseReport.objects.select_related("farm", "farmer", "weather_snapshot").all()
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        return DiseaseReportCreateSerializer if self.action == "create" else DiseaseReportSerializer

    def perform_create(self, serializer):
        report = serializer.save(farmer=self.request.user)
        process_disease_report(report)


class PestReportViewSet(viewsets.ModelViewSet):
    queryset = PestReport.objects.select_related("farm").all()
    serializer_class = PestReportSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)


class ExpertReviewViewSet(viewsets.ModelViewSet):
    queryset = ExpertReview.objects.select_related("disease_report", "expert").all()
    serializer_class = ExpertReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        review = serializer.save(expert=self.request.user)
        report = review.disease_report
        report.status = (
            DiseaseReport.Status.EXPERT_CONFIRMED if review.action == ExpertReview.Action.CONFIRM
            else DiseaseReport.Status.EXPERT_CORRECTED if review.action == ExpertReview.Action.CORRECT
            else report.status
        )
        report.save(update_fields=["status"])


# ---------------------------------------------------------------------------
# Farmer-facing web views
# ---------------------------------------------------------------------------


@login_required
def upload_report(request):
    farms = Farm.objects.filter(owner=request.user)
    if request.method == "POST":
        farm = get_object_or_404(Farm, id=request.POST["farm"], owner=request.user)
        crop_cycle_id = request.POST.get("crop_cycle") or None
        crop_cycle = CropCycle.objects.filter(id=crop_cycle_id, farm=farm).first() if crop_cycle_id else None

        report = DiseaseReport.objects.create(
            farmer=request.user,
            farm=farm,
            crop_cycle=crop_cycle,
            image=request.FILES["image"],
            latitude=request.POST.get("latitude") or farm.latitude,
            longitude=request.POST.get("longitude") or farm.longitude,
        )
        process_disease_report(report)
        return redirect("reports:report_detail", pk=report.pk)

    return render(request, "farmer/upload.html", {"farms": farms})


@login_required
def report_detail(request, pk):
    report = get_object_or_404(DiseaseReport, pk=pk, farmer=request.user)
    return render(request, "farmer/report_detail.html", {"report": report})


@login_required
def report_list(request):
    reports = DiseaseReport.objects.filter(farmer=request.user).select_related("farm")
    return render(request, "farmer/report_list.html", {"reports": reports})


@login_required
def crop_cycles_for_farm(request, farm_id):
    """Small JSON endpoint the upload form uses to populate the crop-cycle
    dropdown once a farm is selected."""
    from django.http import JsonResponse

    farm = get_object_or_404(Farm, id=farm_id, owner=request.user)
    cycles = list(farm.crop_cycles.filter(active=True).values("id", "crop", "variety", "growth_stage"))
    return JsonResponse({"crop_cycles": cycles})
