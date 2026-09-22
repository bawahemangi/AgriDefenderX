from django.contrib import admin

from .models import Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "phone", "preferred_language", "district", "taluka")
    list_filter = ("role", "preferred_language", "district")
    search_fields = ("user__username", "phone", "district")
