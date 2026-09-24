from django.contrib.auth.models import User
from django.db import models

from farms.models import CropCycle, Farm


class WeatherSnapshot(models.Model):
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="weather_snapshots")
    fetched_at = models.DateTimeField(auto_now_add=True)
    temperature_c = models.FloatField()
    humidity_pct = models.FloatField()
    rainfall_mm_7d = models.FloatField(help_text="Rainfall over the last 7 days, mm")
    wind_kmh = models.FloatField()
    source = models.CharField(max_length=30, default="synthetic", help_text="'openweathermap' or 'synthetic'")

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.farm.name} @ {self.fetched_at:%Y-%m-%d %H:%M} ({self.source})"


class PestReport(models.Model):
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="pest_reports")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="pest_reports")
    pest_name = models.CharField(max_length=150, help_text="e.g. Fall armyworm")
    trap_count = models.PositiveIntegerField(default=0)
    latitude = models.FloatField()
    longitude = models.FloatField()
    reported_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-reported_at"]

    def __str__(self):
        return f"{self.pest_name} x{self.trap_count} @ {self.farm.name}"


class DiseaseReport(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending processing"
        ADVISORY_SENT = "advisory_sent", "Advisory sent (auto)"
        FLAGGED_FOR_REVIEW = "flagged", "Flagged for expert review"
        EXPERT_CONFIRMED = "confirmed", "Expert confirmed"
        EXPERT_CORRECTED = "corrected", "Expert corrected"
        REFERRED_LAB = "referred_lab", "Referred to lab"

    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="disease_reports")
    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="disease_reports")
    crop_cycle = models.ForeignKey(CropCycle, on_delete=models.SET_NULL, null=True, blank=True, related_name="disease_reports")
    image = models.ImageField(upload_to="disease_reports/%Y/%m/")

    # Denormalized for fast hotspot map queries even if the farm record changes later.
    latitude = models.FloatField()
    longitude = models.FloatField()

    # -- Image classifier output --
    predicted_class = models.CharField(max_length=150, blank=True)
    crop_detected = models.CharField(max_length=100, blank=True)
    disease_detected = models.CharField(max_length=150, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    classifier_mode = models.CharField(max_length=20, blank=True, help_text="'cnn' or 'demo_heuristic'")

    # -- Risk engine output --
    weather_snapshot = models.ForeignKey(WeatherSnapshot, on_delete=models.SET_NULL, null=True, blank=True)
    risk_score = models.FloatField(null=True, blank=True)
    risk_band = models.CharField(max_length=10, blank=True)

    # -- Advisory (RAG) output --
    advisory_text = models.TextField(blank=True)
    advisory_language = models.CharField(max_length=8, default="en")
    advisory_audio = models.FileField(upload_to="advisory_audio/%Y/%m/", blank=True, null=True)
    advisory_sources = models.JSONField(default=list, blank=True)
    advisory_mode = models.CharField(max_length=30, blank=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.disease_detected or 'Unprocessed'} @ {self.farm.name} ({self.created_at:%Y-%m-%d})"

    @property
    def is_low_confidence(self) -> bool:
        from django.conf import settings
        return self.confidence is not None and self.confidence < settings.LOW_CONFIDENCE_THRESHOLD


class ExpertReview(models.Model):
    """
    Expert/lab validation of a DiseaseReport. This is the model that
    directly satisfies the "expert validation" and "learn from field
    confirmations" requirements: every review here is a labeled training
    example that can be exported (see management command export_training_data)
    to retrain the real CNN in ml/disease_classifier/train.py.
    """

    class Action(models.TextChoices):
        CONFIRM = "confirm", "Confirmed AI diagnosis"
        CORRECT = "correct", "Corrected diagnosis"
        REJECT = "reject", "Rejected (not a valid case)"

    disease_report = models.ForeignKey(DiseaseReport, on_delete=models.CASCADE, related_name="reviews")
    expert = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="expert_reviews")
    action = models.CharField(max_length=10, choices=Action.choices)
    corrected_label = models.CharField(max_length=150, blank=True, help_text="Set only if action=correct")
    notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reviewed_at"]

    def __str__(self):
        return f"{self.get_action_display()} on report #{self.disease_report_id} by {self.expert}"
