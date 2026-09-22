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
    # (district, taluka, approx center lat, approx center lng)
    ("Jalgaon",    "Jalgaon",    21.0077, 75.5626),
    ("Nashik",     "Niphad",     19.9975, 73.7898),
    ("Pune",       "Haveli",     18.5204, 73.8567),
    ("Dhule",      "Shirpur",    20.9042, 74.7749),
    ("Ahmednagar", "Rahuri",     19.0952, 74.7496),
    ("Solapur",    "Pandharpur", 17.6805, 75.3214),
    ("Kolhapur",   "Hatkanangle",16.6949, 74.2310),
    ("Aurangabad", "Gangapur",   19.8762, 75.3433),
]

CROPS = ["Tomato", "Potato", "Corn Maize", "Grape", "Sugarcane", "Cotton", "Onion", "Soybean"]
VARIETIES = ["Local", "Hybrid-1", "Hybrid-2", "Improved", "Desi"]

# Realistic Maharashtra farmer profiles
FARMER_PROFILES = [
    {"first_name": "Ramesh",    "last_name": "Patil",      "phone": "9823041567", "village": "Wakad"},
    {"first_name": "Suresh",    "last_name": "Jadhav",     "phone": "9765234801", "village": "Pimpri"},
    {"first_name": "Santosh",   "last_name": "Shinde",     "phone": "9876543210", "village": "Chinchwad"},
    {"first_name": "Vijay",     "last_name": "More",       "phone": "9112345678", "village": "Alandi"},
    {"first_name": "Prakash",   "last_name": "Deshmukh",   "phone": "9988776655", "village": "Dehu"},
    {"first_name": "Raju",      "last_name": "Bhosale",    "phone": "8800991234", "village": "Talegaon"},
    {"first_name": "Ganesh",    "last_name": "Waghmare",   "phone": "9321456789", "village": "Indapur"},
    {"first_name": "Dinesh",    "last_name": "Pawar",      "phone": "9870001122", "village": "Baramati"},
    {"first_name": "Mahesh",    "last_name": "Kulkarni",   "phone": "9654321098", "village": "Shirur"},
    {"first_name": "Anil",      "last_name": "Gaikwad",    "phone": "9512345670", "village": "Junnar"},
    {"first_name": "Balaji",    "last_name": "Kale",       "phone": "9445678901", "village": "Manchar"},
    {"first_name": "Sanjay",    "last_name": "Nimbalkar",  "phone": "9334512678", "village": "Phaltan"},
    {"first_name": "Vikas",     "last_name": "Salunkhe",   "phone": "9224567890", "village": "Wai"},
    {"first_name": "Rajendra",  "last_name": "Thorat",     "phone": "9112233445", "village": "Satara"},
    {"first_name": "Dattatray", "last_name": "Mane",       "phone": "9001122334", "village": "Karad"},
]

SOIL_TYPES = ["Black (Vertisol)", "Red laterite", "Loamy alluvial", "Sandy loam", "Medium black"]


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
            district, taluka, lat0, lng0 = DISTRICTS[i % len(DISTRICTS)]
            fp = FARMER_PROFILES[i]
            username = f"farmer{i+1}"
            farmer, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": fp["first_name"],
                    "last_name": fp["last_name"],
                    "email": f"{username}@krishi.mh.gov.in",
                },
            )
            farmer.first_name = fp["first_name"]
            farmer.last_name = fp["last_name"]
            farmer.set_password("demo1234")
            farmer.save()
            Profile.objects.update_or_create(
                user=farmer,
                defaults={
                    "role": Profile.Role.FARMER,
                    "district": district,
                    "taluka": taluka,
                    "phone": fp["phone"],
                    "preferred_language": random.choice(["en", "mr", "hi"]),
                },
            )

            lat = lat0 + rng.normal(0, 0.18)
            lng = lng0 + rng.normal(0, 0.18)
            farm_name = f"{fp['last_name']} {fp['village']} Farm"
            farm, _ = Farm.objects.get_or_create(
                owner=farmer, name=farm_name,
                defaults={
                    "latitude": lat,
                    "longitude": lng,
                    "area_acres": round(random.uniform(1.5, 12.0), 1),
                    "district": district,
                    "taluka": taluka,
                    "village": fp["village"],
                    "soil_type": random.choice(SOIL_TYPES),
                },
            )
            farms.append(farm)

            crop = random.choice(CROPS)
            CropCycle.objects.get_or_create(
                farm=farm, crop=crop,
                defaults={
                    "variety": random.choice(VARIETIES),
                    "sowing_date": dt.date.today() - dt.timedelta(days=random.randint(10, 120)),
                    "growth_stage": random.choice(CropCycle.GrowthStage.values),
                },
            )

            # Realistic pest variation — not all farms have same pest
            pest = random.choice(["Fall armyworm", "Aphids", "Whitefly", "Bollworm", "Thrips"])
            PestReport.objects.get_or_create(
                farmer=farmer, farm=farm, pest_name=pest,
                defaults={
                    "trap_count": random.randint(0, 40),
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
