"""
Plain-Python geo helpers (haversine distance) -- deliberately NOT using
PostGIS/GeoDjango, to keep the project runnable on SQLite with zero native
geo-library setup. Fine for a hackathon's data volume; if you outgrow it
(large numbers of reports, need for real spatial indexes), migrate to
PostGIS and replace these functions with ORM .annotate(distance=...) calls
-- the call sites in services.py and dashboard/views.py won't need to
change much since they just consume a list of (report, distance_km) pairs.
"""
from __future__ import annotations

import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def count_nearby_confirmed_cases(latitude: float, longitude: float, days: int = 14, radius_km: float = 10.0) -> int:
    import datetime as dt

    from django.utils import timezone

    from .models import DiseaseReport

    since = timezone.now() - dt.timedelta(days=days)
    candidates = DiseaseReport.objects.filter(
        created_at__gte=since,
        status__in=[
            DiseaseReport.Status.ADVISORY_SENT,
            DiseaseReport.Status.EXPERT_CONFIRMED,
            DiseaseReport.Status.EXPERT_CORRECTED,
        ],
    ).exclude(disease_detected__iexact="healthy")

    return sum(
        1 for r in candidates
        if haversine_km(latitude, longitude, r.latitude, r.longitude) <= radius_km
    )


def cluster_hotspots(reports, radius_km: float = 5.0) -> list[dict]:
    """Simple greedy clustering of confirmed-disease report points into
    hotspots, for the dashboard summary view. Not a substitute for a real
    spatial clustering algorithm (e.g. DBSCAN) at scale, but transparent
    and dependency-free for a hackathon-sized dataset."""
    points = [r for r in reports if r.latitude is not None and r.longitude is not None]
    clusters: list[dict] = []

    for r in points:
        placed = False
        for cluster in clusters:
            if haversine_km(r.latitude, r.longitude, cluster["latitude"], cluster["longitude"]) <= radius_km:
                cluster["reports"].append(r)
                n = len(cluster["reports"])
                cluster["latitude"] = (cluster["latitude"] * (n - 1) + r.latitude) / n
                cluster["longitude"] = (cluster["longitude"] * (n - 1) + r.longitude) / n
                placed = True
                break
        if not placed:
            clusters.append({"latitude": r.latitude, "longitude": r.longitude, "reports": [r]})

    return sorted(clusters, key=lambda c: len(c["reports"]), reverse=True)
