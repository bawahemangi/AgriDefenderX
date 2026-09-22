"""
Usage: python manage.py export_training_data --out ./ml/disease_classifier/data/train

Walks every DiseaseReport that has an ExpertReview, and copies its image
into an ImageFolder-style directory named after the *confirmed* label
(the expert's corrected_label if they corrected it, otherwise the
original AI prediction if the expert confirmed it). Rejected reports are
skipped entirely.

This is the concrete mechanism behind "learn from field confirmations":
run this periodically, then re-run ml/disease_classifier/train.py against
the growing, real-world-labeled dataset it produces, so accuracy improves
over time instead of staying frozen at whatever PlantVillage alone gives you.
"""
import shutil
from pathlib import Path

from django.core.management.base import BaseCommand

from reports.models import ExpertReview


class Command(BaseCommand):
    help = "Export expert-confirmed/corrected disease reports as a labeled training dataset."

    def add_arguments(self, parser):
        parser.add_argument("--out", type=str, default="./ml/disease_classifier/data/train")

    def handle(self, *args, **options):
        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)

        reviews = ExpertReview.objects.select_related("disease_report").exclude(action=ExpertReview.Action.REJECT)
        exported = 0

        for review in reviews:
            report = review.disease_report
            if not report.image:
                continue

            label = review.corrected_label if review.action == ExpertReview.Action.CORRECT else report.predicted_class
            if not label:
                continue

            label_dir = out_dir / label.replace(" ", "_")
            label_dir.mkdir(parents=True, exist_ok=True)
            dest = label_dir / f"report_{report.id}{Path(report.image.name).suffix}"
            shutil.copy(report.image.path, dest)
            exported += 1

        self.stdout.write(self.style.SUCCESS(
            f"Exported {exported} labeled image(s) to {out_dir}. "
            f"Next: python ml/disease_classifier/train.py --data-dir {out_dir.parent}"
        ))
