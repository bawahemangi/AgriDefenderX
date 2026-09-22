from rest_framework import serializers

from .models import DiseaseReport, ExpertReview, PestReport, WeatherSnapshot


class WeatherSnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherSnapshot
        fields = ["id", "temperature_c", "humidity_pct", "rainfall_mm_7d", "wind_kmh", "source", "fetched_at"]


class DiseaseReportSerializer(serializers.ModelSerializer):
    weather = WeatherSnapshotSerializer(source="weather_snapshot", read_only=True)
    farmer_username = serializers.CharField(source="farmer.username", read_only=True)
    farm_name = serializers.CharField(source="farm.name", read_only=True)
    district = serializers.CharField(source="farm.district", read_only=True)

    class Meta:
        model = DiseaseReport
        fields = [
            "id", "farmer_username", "farm", "farm_name", "district", "crop_cycle",
            "image", "latitude", "longitude",
            "predicted_class", "crop_detected", "disease_detected", "confidence", "classifier_mode",
            "risk_score", "risk_band", "weather",
            "advisory_text", "advisory_language", "advisory_sources", "advisory_mode",
            "status", "created_at",
        ]
        read_only_fields = [f for f in fields if f not in ("image", "farm", "crop_cycle", "latitude", "longitude")]


class DiseaseReportCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiseaseReport
        fields = ["farm", "crop_cycle", "image", "latitude", "longitude"]


class PestReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = PestReport
        fields = ["id", "farm", "pest_name", "trap_count", "latitude", "longitude", "reported_at", "notes"]
        read_only_fields = ["id", "reported_at"]


class ExpertReviewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpertReview
        fields = ["id", "disease_report", "expert", "action", "corrected_label", "notes", "reviewed_at"]
        read_only_fields = ["id", "reviewed_at"]
