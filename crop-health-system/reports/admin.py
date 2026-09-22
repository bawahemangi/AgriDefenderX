from django.contrib import admin
from django.utils.html import format_html

from .models import DiseaseReport, ExpertReview, PestReport, WeatherSnapshot


class ExpertReviewInline(admin.TabularInline):
    """
    Lets an expert/officer confirm, correct, or reject a diagnosis directly
    from the report's admin page. Every row created here is a labeled
    training example -- see management command `export_training_data`,
    which turns confirmed/corrected reviews into an ImageFolder dataset
    ready for ml/disease_classifier/train.py. This is the "learn from
    field confirmations" loop from the problem statement.
    """
    model = ExpertReview
    extra = 1
    fields = ("expert", "action", "corrected_label", "notes", "reviewed_at")
    readonly_fields = ("reviewed_at",)


@admin.register(DiseaseReport)
class DiseaseReportAdmin(admin.ModelAdmin):
    list_display = (
        "id", "thumbnail", "farmer", "farm", "district",
        "disease_detected", "confidence_pct", "classifier_mode",
        "risk_band_badge", "status", "created_at",
    )
    list_filter = ("status", "risk_band", "classifier_mode", "farm__district", "crop_detected")
    search_fields = ("disease_detected", "crop_detected", "farmer__username", "farm__name", "farm__district")
    readonly_fields = (
        "predicted_class", "crop_detected", "disease_detected", "confidence",
        "classifier_mode", "risk_score", "risk_band", "advisory_text",
        "advisory_language", "advisory_sources", "advisory_mode",
        "created_at", "updated_at", "image_preview",
    )
    inlines = [ExpertReviewInline]
    actions = ["mark_confirmed", "mark_referred_to_lab"]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Submission", {"fields": ("farmer", "farm", "crop_cycle", "image", "image_preview", "latitude", "longitude")}),
        ("AI Diagnosis", {"fields": ("predicted_class", "crop_detected", "disease_detected", "confidence", "classifier_mode")}),
        ("Risk Assessment", {"fields": ("weather_snapshot", "risk_score", "risk_band")}),
        ("Advisory", {"fields": ("advisory_text", "advisory_language", "advisory_sources", "advisory_mode")}),
        ("Status", {"fields": ("status", "created_at", "updated_at")}),
    )

    @admin.display(description="District")
    def district(self, obj):
        return obj.farm.district

    @admin.display(description="Confidence")
    def confidence_pct(self, obj):
        if obj.confidence is None:
            return "-"
        color = "#3F7D58" if obj.confidence >= 0.7 else ("#C98A1D" if obj.confidence >= 0.5 else "#C1440E")
        pct_text = f"{obj.confidence:.0%}"
        return format_html('<span style="color:{}; font-weight:600">{}</span>', color, pct_text)

    @admin.display(description="Risk")
    def risk_band_badge(self, obj):
        colors = {"HIGH": "#C1440E", "MEDIUM": "#C98A1D", "LOW": "#3F7D58"}
        color = colors.get(obj.risk_band, "#666")
        return format_html('<span style="color:{}; font-weight:700">{}</span>', color, obj.risk_band or "-")

    @admin.display(description="Photo")
    def thumbnail(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="height:40px;border-radius:4px" />', obj.image.url)
        return "-"

    @admin.display(description="Preview")
    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:300px;border-radius:8px" />', obj.image.url)
        return "-"

    @admin.action(description="Mark selected as expert-confirmed")
    def mark_confirmed(self, request, queryset):
        for report in queryset:
            ExpertReview.objects.create(disease_report=report, expert=request.user, action=ExpertReview.Action.CONFIRM)
            report.status = DiseaseReport.Status.EXPERT_CONFIRMED
            report.save(update_fields=["status"])
        self.message_user(request, f"{queryset.count()} report(s) marked confirmed.")

    @admin.action(description="Refer selected to laboratory")
    def mark_referred_to_lab(self, request, queryset):
        queryset.update(status=DiseaseReport.Status.REFERRED_LAB)
        self.message_user(request, f"{queryset.count()} report(s) referred to lab.")


@admin.register(PestReport)
class PestReportAdmin(admin.ModelAdmin):
    list_display = ("pest_name", "trap_count", "farm", "farmer", "reported_at")
    list_filter = ("pest_name", "farm__district")
    search_fields = ("pest_name", "farm__name", "farmer__username")


@admin.register(WeatherSnapshot)
class WeatherSnapshotAdmin(admin.ModelAdmin):
    list_display = ("farm", "temperature_c", "humidity_pct", "rainfall_mm_7d", "wind_kmh", "source", "fetched_at")
    list_filter = ("source",)


@admin.register(ExpertReview)
class ExpertReviewAdmin(admin.ModelAdmin):
    list_display = ("disease_report", "expert", "action", "corrected_label", "reviewed_at")
    list_filter = ("action",)
