"""
This module is the seam between the Django app and the ml/ package.
Given a freshly-created DiseaseReport (image + farm already saved), it:

    1. Runs the image classifier (ml/disease_classifier)
    2. Fetches/reuses today's weather for the farm (reports/weather.py)
    3. Counts nearby recent confirmed cases (reports/geo.py) and pest
       trap activity (reports/models.PestReport) for this farm
    4. Runs the risk model (ml/risk_model) on the combined feature set
    5. Generates a grounded advisory via RAG (ml/advisory_rag)
    6. Sets the report's status: auto-advisory, or flagged for expert
       review if confidence is low or risk is high

This keeps all the "combine weather + crop stage + pest history + image
confidence into one actionable alert" logic the problem statement asks
for in one auditable place.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

from django.db.models import Sum
from django.utils import timezone

from .geo import count_nearby_confirmed_cases
from .models import DiseaseReport, PestReport
from .weather import get_or_fetch_weather

# ml/ lives as a sibling of the Django project root, not inside any app --
# make its subpackages importable.
BASE_DIR = Path(__file__).resolve().parent.parent
for sub in ("disease_classifier", "risk_model", "advisory_rag", "economic_engine"):
    path = str(BASE_DIR / "ml" / sub)
    if path not in sys.path:
        sys.path.insert(0, path)


def _recent_pest_count(farm, days: int = 7) -> int:
    since = timezone.now() - dt.timedelta(days=days)
    total = PestReport.objects.filter(farm=farm, reported_at__gte=since).aggregate(total=Sum("trap_count"))["total"]
    return total or 0


def process_disease_report(report: DiseaseReport, language: str = None) -> DiseaseReport:
    # -- 1. Image classification --
    import infer as classifier_infer  # ml/disease_classifier/infer.py

    result = classifier_infer.classify_image(report.image.path)
    report.predicted_class = result["predicted_class"]
    report.crop_detected = result["crop"]
    report.disease_detected = result["disease"]
    report.confidence = result["confidence"]
    report.classifier_mode = result["mode"]

    # -- 2. Weather --
    weather = get_or_fetch_weather(report.farm)
    report.weather_snapshot = weather

    # -- 3. Contextual features --
    crop_cycle = report.crop_cycle
    growth_stage_code = crop_cycle.growth_stage_code if crop_cycle else 0
    days_since_sowing = crop_cycle.days_since_sowing if crop_cycle else 30
    nearby_cases = count_nearby_confirmed_cases(report.latitude, report.longitude)
    pest_count = _recent_pest_count(report.farm)
    is_healthy_prediction = "healthy" in result["predicted_class"].lower()

    # -- 4. Risk scoring --
    import predict as risk_predict  # ml/risk_model/predict.py

    risk = risk_predict.predict_risk({
        "temperature_c": weather.temperature_c,
        "humidity_pct": weather.humidity_pct,
        "rainfall_mm_7d": weather.rainfall_mm_7d,
        "wind_kmh": weather.wind_kmh,
        "days_since_sowing": days_since_sowing,
        "growth_stage_code": growth_stage_code,
        "pest_trap_count_7d": pest_count,
        "nearby_confirmed_cases_14d": nearby_cases,
        "image_model_confidence": result["confidence"],
        "image_model_flagged_disease": 0 if is_healthy_prediction else 1,
    })
    report.risk_score = risk["risk_score"]
    report.risk_band = risk["risk_band"]

    # -- 5. Advisory (RAG) --
    import generate as advisory_generate  # ml/advisory_rag/generate.py

    if not language:
        language = report.farmer.profile.preferred_language if hasattr(report.farmer, "profile") else "en"
    
    advisory = advisory_generate.generate_advisory(
        crop=result["crop"],
        disease=result["disease"],
        growth_stage=crop_cycle.growth_stage if crop_cycle else "",
        risk_band=risk["risk_band"],
        language=language,
        low_confidence=report.is_low_confidence,
    )
    report.advisory_text = advisory.text
    report.advisory_language = advisory.language
    report.advisory_sources = advisory.sources
    report.advisory_mode = advisory.generation_mode

    # -- 5b. Generate Audio --
    if report.advisory_text:
        try:
            from gtts import gTTS
            from django.core.files.base import ContentFile
            import tempfile
            import os
            import uuid

            tts = gTTS(text=report.advisory_text, lang=report.advisory_language)
            
            fd, temp_path = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)
            tts.save(temp_path)
            
            with open(temp_path, "rb") as f:
                filename = f"advisory_{uuid.uuid4().hex[:8]}_{report.advisory_language}.mp3"
                report.advisory_audio.save(filename, ContentFile(f.read()), save=False)
                
            os.remove(temp_path)
        except Exception as e:
            print(f"Audio generation failed: {e}")

    # -- 6. Routing --
    if report.is_low_confidence or report.risk_band == "HIGH":
        report.status = DiseaseReport.Status.FLAGGED_FOR_REVIEW
    else:
        report.status = DiseaseReport.Status.ADVISORY_SENT

    # -- 7. Economic Decision Intelligence --
    try:
        from calculate import calculate_economics  # ml/economic_engine/calculate.py

        area_acres = report.farm.area_acres if report.farm.area_acres else 1.0
        econ = calculate_economics(
            crop=result["crop"],
            disease=result["disease"],
            risk_band=risk["risk_band"],
            area_acres=area_acres,
            confidence=result["confidence"],
            is_healthy=is_healthy_prediction,
        )
        report.econ_expected_yield_value = econ.expected_yield_value
        report.econ_current_loss_value   = econ.current_loss_value
        report.econ_treatment_cost       = econ.treatment_cost
        report.econ_expected_recovery    = econ.expected_recovery
        report.econ_net_benefit          = econ.net_benefit
        report.econ_roi_pct              = econ.roi_pct
        report.econ_verdict              = econ.verdict
        report.econ_rationale            = econ.rationale
    except Exception as e:
        print(f"Economic engine failed: {e}")

    # -- 8. Range-based economic decision (reports/economics.py) --
    try:
        from .economics import (
            estimate_decision,
            severity_from_risk_band,
            fetch_mandi_price,
        )
        from .economics import _lookup_dict as _ec_lookup, _CROP_PARAMS

        crop_key  = result["crop"].lower().strip()
        crop_defaults = _lookup_dict_safe(crop_key, _CROP_PARAMS)

        # Resolve yield and price: crop_cycle overrides > JSON defaults
        ypa = (
            report.crop_cycle.expected_yield_per_acre
            if report.crop_cycle and report.crop_cycle.expected_yield_per_acre
            else crop_defaults.get("yield_per_acre", 15)
        )
        # Try Agmarknet price first, then cycle override, then JSON default
        market_price = fetch_mandi_price(result["crop"])
        ppu = (
            market_price
            or (
                report.crop_cycle.expected_price_per_unit
                if report.crop_cycle and report.crop_cycle.expected_price_per_unit
                else None
            )
            or crop_defaults.get("price_per_unit", 20.0)
        )

        severity = severity_from_risk_band(risk["risk_band"])
        area = report.farm.area_acres if report.farm.area_acres and report.farm.area_acres > 0 else None

        est = estimate_decision(
            crop=result["crop"],
            disease=result["disease"],
            severity=severity,
            area_acres=area or 1.0,
            yield_per_acre=ypa,
            price_per_unit=ppu,
            confidence=result["confidence"],
        )
        if est is not None and area is not None:
            report.economic_estimate = est
        elif est is not None:
            # area was missing — store estimate but mark it
            est["area_missing"] = True
            report.economic_estimate = est
    except Exception as e:
        print(f"Range-based economic estimate failed: {e}")

    report.save()
    return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lookup_dict_safe(key: str, table: dict) -> dict:
    """Partial-match crop lookup, returns empty dict on miss."""
    if key in table:
        return table[key]
    for k, v in table.items():
        if k.startswith("_"):
            continue
        if k in key or key in k:
            return v
    return table.get("_generic", {})
