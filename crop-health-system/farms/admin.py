from django.contrib import admin

from .models import CropCycle, Farm


class CropCycleInline(admin.TabularInline):
    model = CropCycle
    extra = 0


@admin.register(Farm)
class FarmAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "district", "taluka", "area_acres", "created_at")
    list_filter = ("district", "taluka", "soil_type")
    search_fields = ("name", "owner__username", "village")
    inlines = [CropCycleInline]


@admin.register(CropCycle)
class CropCycleAdmin(admin.ModelAdmin):
    list_display = ("crop", "variety", "farm", "sowing_date", "growth_stage", "active")
    list_filter = ("crop", "growth_stage", "active")
    search_fields = ("crop", "variety", "farm__name")
