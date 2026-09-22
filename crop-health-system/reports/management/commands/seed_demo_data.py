"""
Usage: python manage.py seed_demo_data

Creates demo users, farms, crop cycles, and a batch of processed disease
reports across a few Maharashtra districts so the officer dashboard and
hotspot map have something to show immediately -- essential for a live
hackathon demo. Uses small synthetically generated leaf-colored images
(no external image dataset needed) run through the real pipeline
(classifier -> weather -> risk -> advisory), so the demo data is produced
exactly the same way real submissions would be.

Safe to re-run -- uses get_or_create for users/farms.
"""
import datetime as dt
import io
import random

from django.utils import timezone as dj_timezone

import numpy as np
from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from PIL import Image

from accounts.models import Profile
from farms.models import CropCycle, Farm
from reports.models import DiseaseReport, PestReport
from reports.services import process_disease_report

DISTRICTS = [
    # (district, approx center lat, approx center lng)
    ("Jalgaon", 21.0077, 75.5626),
    ("Nashik", 19.9975, 73.7898),
    ("Pune", 18.5204, 73.8567),
    ("Dhule", 20.9042, 74.7749),
    ("Ahmednagar", 19.0952, 74.7496),
]

CROPS = ["Tomato", "Potato", "Corn Maize", "Grape", "Squash", "Apple"]
VARIETIES = ["Local", "Hybrid-1", "Hybrid-2", "Improved"]


def _synthetic_leaf_image(archetype: str, seed: int) -> ContentFile:
    """Generates a small image whose color statistics roughly match a
    disease archetype, so the demo classifier (features.py-based) produces
    varied, non-random-looking predictions rather than everything landing
    on one class."""
    rng = np.random.default_rng(seed)
    base = {
        "healthy": (60, 150, 60),
        "blight": (130, 110, 60),
        "rust": (150, 95, 45),
        "mildew": (150, 160, 145),
    }.get(archetype, (110, 110, 70))

    arr = np.zeros((128, 128, 3), dtype=np.uint8)
    for c in range(3):
        arr[:, :, c] = np.clip(base[c] + rng.normal(0, 18, (128, 128)), 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG")
    return ContentFile(buf.getvalue(), name=f"demo_{archetype}_{seed}.jpg")


class Command(BaseCommand):
    help = "Seed demo farmers, farms, crop cycles, and processed disease reports."

    def add_arguments(self, parser):
        parser.add_argument("--reports", type=int, default=60)

    def handle(self, *args, **options):
        random.seed(42)
        rng = np.random.default_rng(42)

        expert, _ = User.objects.get_or_create(username="expert1", defaults={"is_staff": True})
        expert.set_password("demo1234")
        expert.save()
        Profile.objects.update_or_create(user=expert, defaults={"role": Profile.Role.EXPERT})

        officer, _ = User.objects.get_or_create(username="officer1", defaults={"is_staff": True, "is_superuser": True})
        officer.set_password("demo1234")
        officer.save()
        Profile.objects.update_or_create(user=officer, defaults={"role": Profile.Role.OFFICER})

        farms = []
        for i in range(15):
            district, lat0, lng0 = DISTRICTS[i % len(DISTRICTS)]
            username = f"farmer{i+1}"
            farmer, _ = User.objects.get_or_create(username=username, defaults={"first_name": f"Farmer {i+1}"})
            farmer.set_password("demo1234")
            farmer.save()
            Profile.objects.update_or_create(
                user=farmer, defaults={"role": Profile.Role.FARMER, "district": district, "preferred_language": "en"}
            )

            farm, _ = Farm.objects.get_or_create(
                owner=farmer, name=f"{district} Farm {i+1}",
                defaults={
                    "latitude": lat0 + rng.normal(0, 0.15),
                    "longitude": lng0 + rng.normal(0, 0.15),
                    "area_acres": round(random.uniform(1, 8), 1),
                    "district": district,
                    "soil_type": random.choice(["Black soil", "Red soil", "Loamy", "Sandy loam"]),
                },
            )
            farms.append(farm)

            crop = random.choice(CROPS)
            CropCycle.objects.get_or_create(
                farm=farm, crop=crop,
                defaults={
                    "variety": random.choice(VARIETIES),
                    "sowing_date": dt.date.today() - dt.timedelta(days=random.randint(10, 100)),
                    "growth_stage": random.choice(CropCycle.GrowthStage.values),
                },
            )

            PestReport.objects.get_or_create(
                farmer=farmer, farm=farm, pest_name="Fall armyworm",
                defaults={
                    "trap_count": random.randint(0, 25),
                    "latitude": farm.latitude, "longitude": farm.longitude,
                },
            )

        self.stdout.write(self.style.SUCCESS(f"{len(farms)} farms ready. Generating disease reports..."))

        archetypes = ["healthy", "blight", "rust", "mildew"]
        n_reports = options["reports"]
        created = 0
        for i in range(n_reports):
            farm = random.choice(farms)
            crop_cycle = farm.crop_cycles.first()
            archetype = random.choices(archetypes, weights=[0.35, 0.35, 0.15, 0.15])[0]

            report = DiseaseReport.objects.create(
                farmer=farm.owner,
                farm=farm,
                crop_cycle=crop_cycle,
                image=_synthetic_leaf_image(archetype, seed=i),
                latitude=farm.latitude + rng.normal(0, 0.01),
                longitude=farm.longitude + rng.normal(0, 0.01),
                created_at=dj_timezone.now() - dt.timedelta(days=random.randint(0, 29)),
            )
            process_disease_report(report)
            # created_at gets overwritten by auto_now_add on save() inside
            # process_disease_report; backdate it again for a realistic timeline.
            DiseaseReport.objects.filter(pk=report.pk).update(
                created_at=dj_timezone.now() - dt.timedelta(days=random.randint(0, 29))
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created} disease reports.\n"
            f"Log in at /admin/ with officer1 / demo1234 (or expert1 / demo1234).\n"
            f"View the dashboard at /dashboard/."
        ))
