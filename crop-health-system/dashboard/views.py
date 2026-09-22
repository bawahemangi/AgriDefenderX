import datetime as dt

from django.utils import timezone as dj_timezone

from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render

from reports.geo import cluster_hotspots
from reports.models import DiseaseReport


def _is_staff(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(_is_staff)
def officer_dashboard(request):
    reports = DiseaseReport.objects.select_related("farm", "farmer").exclude(status="pending")

    district = request.GET.get("district")
    crop = request.GET.get("crop")
    disease = request.GET.get("disease")
    risk = request.GET.get("risk")
    days = int(request.GET.get("days", 30))

    since = dj_timezone.now() - dt.timedelta(days=days)
    reports = reports.filter(created_at__gte=since)

    if district:
        reports = reports.filter(farm__district=district)
    if crop:
        reports = reports.filter(crop_detected=crop)
    if disease:
        reports = reports.filter(disease_detected=disease)
    if risk:
        reports = reports.filter(risk_band=risk)

    stats = {
        "total_reports": reports.count(),
        "high_risk": reports.filter(risk_band="HIGH").count(),
        "pending_review": reports.filter(status=DiseaseReport.Status.FLAGGED_FOR_REVIEW).count(),
        "farmers_reached": reports.values("farmer").distinct().count(),
    }

    disease_distribution = list(
        reports.exclude(disease_detected="").values("disease_detected")
        .annotate(count=Count("id")).order_by("-count")[:8]
    )
    district_distribution = list(
        reports.values("farm__district").annotate(count=Count("id")).order_by("-count")[:8]
    )

    all_districts = DiseaseReport.objects.values_list("farm__district", flat=True).distinct().order_by("farm__district")
    all_crops = DiseaseReport.objects.exclude(crop_detected="").values_list("crop_detected", flat=True).distinct().order_by("crop_detected")
    all_diseases = DiseaseReport.objects.exclude(disease_detected="").values_list("disease_detected", flat=True).distinct().order_by("disease_detected")

    # Farmer directory
    farmer_qs = (
        User.objects.filter(profile__role="farmer")
        .select_related("profile")
        .prefetch_related("farms", "disease_reports")
        .order_by("last_name", "first_name")
    )
    farmer_directory = []
    for f in farmer_qs:
        farm = f.farms.first()
        latest = f.disease_reports.order_by("-created_at").first()
        farmer_directory.append({
            "user": f,
            "farm": farm,
            "latest_report": latest,
            "report_count": f.disease_reports.count(),
        })

    context = {
        "stats": stats,
        "disease_distribution": disease_distribution,
        "district_distribution": district_distribution,
        "reports": reports.order_by("-created_at")[:100],
        "filters": {"district": district, "crop": crop, "disease": disease, "risk": risk, "days": days},
        "all_districts": [d for d in all_districts if d],
        "all_crops": [c for c in all_crops if c],
        "all_diseases": [d for d in all_diseases if d],
        "farmer_directory": farmer_directory,
    }
    return render(request, "dashboard/index.html", context)


@login_required
@user_passes_test(_is_staff)
def hotspot_geojson(request):
    reports = DiseaseReport.objects.select_related("farm").exclude(status="pending").exclude(disease_detected__iexact="healthy")
    days = int(request.GET.get("days", 30))
    since = dj_timezone.now() - dt.timedelta(days=days)
    reports = reports.filter(created_at__gte=since)

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [r.longitude, r.latitude]},
            "properties": {
                "id": r.id,
                "disease": r.disease_detected,
                "crop": r.crop_detected,
                "risk_band": r.risk_band,
                "district": r.farm.district,
                "farm": r.farm.name,
                "farmer": r.farmer.get_full_name() or r.farmer.username,
                "created_at": r.created_at.strftime("%Y-%m-%d"),
            },
        }
        for r in reports
    ]

    clusters = cluster_hotspots(list(reports))
    cluster_summary = [
        {"latitude": c["latitude"], "longitude": c["longitude"], "count": len(c["reports"])}
        for c in clusters if len(c["reports"]) >= 2
    ]

    return JsonResponse({
        "type": "FeatureCollection",
        "features": features,
        "hotspot_clusters": cluster_summary,
    })
