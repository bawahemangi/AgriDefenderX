from django.contrib.auth.models import User
from django.db import models


class Farm(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="farms")
    name = models.CharField(max_length=150)
    latitude = models.FloatField()
    longitude = models.FloatField()
    area_acres = models.FloatField(help_text="Farm area in acres")
    district = models.CharField(max_length=100)
    taluka = models.CharField(max_length=100, blank=True)
    village = models.CharField(max_length=100, blank=True)
    soil_type = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.owner.username}, {self.district})"


class CropCycle(models.Model):
    class GrowthStage(models.TextChoices):
        VEGETATIVE = "vegetative", "Vegetative"
        FLOWERING = "flowering", "Flowering"
        FRUITING = "fruiting", "Fruiting"
        MATURITY = "maturity", "Maturity"

    STAGE_CODE = {
        GrowthStage.VEGETATIVE: 0,
        GrowthStage.FLOWERING: 1,
        GrowthStage.FRUITING: 2,
        GrowthStage.MATURITY: 3,
    }

    farm = models.ForeignKey(Farm, on_delete=models.CASCADE, related_name="crop_cycles")
    crop = models.CharField(max_length=100, help_text="e.g. Tomato, Potato, Cotton")
    variety = models.CharField(max_length=100, blank=True)
    sowing_date = models.DateField()
    growth_stage = models.CharField(max_length=20, choices=GrowthStage.choices, default=GrowthStage.VEGETATIVE)
    active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.crop} @ {self.farm.name} (sown {self.sowing_date})"

    @property
    def days_since_sowing(self) -> int:
        from datetime import date
        return (date.today() - self.sowing_date).days

    @property
    def growth_stage_code(self) -> int:
        return self.STAGE_CODE.get(self.growth_stage, 0)
