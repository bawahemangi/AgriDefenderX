"""
Guest scan view — runs the full ML pipeline (image classify + risk + advisory)
without requiring the user to be logged in or have a farm record.

This is the entry point for the public /scan/ page.
"""
from __future__ import annotations

import sys
import tempfile
import os
import uuid
from pathlib import Path

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render
from django.conf import settings


# Make ml subpackages importable (same pattern as reports/services.py)
BASE_DIR = Path(__file__).resolve().parent.parent
for sub in ("disease_classifier", "risk_model", "advisory_rag"):
    p = str(BASE_DIR / "ml" / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def scan_page(request):
    """Renders the public crop-scan landing page."""
    return render(request, "farmer/scan.html")


@require_POST
def analyse_image(request):
    """
    AJAX endpoint called by the scan page.
    Accepts: image (file), language (str), voice_text (str, optional)
    Returns: JSON with disease, crop, risk, advisory, audio_url
    """
    image_file = request.FILES.get("image")
    # Language priority: POST param → Django session (set_language) → 'en'
    session_lang = request.session.get("_language", request.LANGUAGE_CODE or "en")
    language   = request.POST.get("language") or session_lang
    # Normalise: only support en/mr/hi
    if language not in ("en", "mr", "hi"):
        language = "en"
    voice_text = request.POST.get("voice_text", "").strip()

    if not image_file:
        return JsonResponse({"error": "No image provided."}, status=400)

    # ── 1. Save image to a temp file so the classifier can open it ──────
    suffix = Path(image_file.name).suffix or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(fd)
        with open(tmp_path, "wb") as f:
            for chunk in image_file.chunks():
                f.write(chunk)

        # ── 2. Image classification ──────────────────────────────────────
        import infer as classifier_infer
        result = classifier_infer.classify_image(tmp_path)

    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    crop            = result.get("crop", "Unknown")
    disease         = result.get("disease", "Unknown")
    confidence      = result.get("confidence", 0.0)
    classifier_mode = result.get("mode", "")
    is_healthy      = "healthy" in result.get("predicted_class", "").lower()

    # ── 3. Risk model (lightweight — use defaults for guest with no farm) ─
    import predict as risk_predict
    risk = risk_predict.predict_risk({
        "temperature_c":             28.0,   # Maharashtra seasonal average
        "humidity_pct":              70.0,
        "rainfall_mm_7d":            20.0,
        "wind_kmh":                  12.0,
        "days_since_sowing":         45,
        "growth_stage_code":         2,
        "pest_trap_count_7d":        0,
        "nearby_confirmed_cases_14d":0,
        "image_model_confidence":    confidence,
        "image_model_flagged_disease": 0 if is_healthy else 1,
    })
    risk_score = risk["risk_score"]
    risk_band  = risk["risk_band"]

    # ── 4. Advisory (RAG) ───────────────────────────────────────────────
    import generate as advisory_generate
    low_conf = confidence < getattr(settings, "LOW_CONFIDENCE_THRESHOLD", 0.20)
    advisory = advisory_generate.generate_advisory(
        crop=crop,
        disease=disease,
        growth_stage="",
        risk_band=risk_band,
        language=language,
        low_confidence=low_conf,
    )

    # ── 5. Append voice_text context to advisory if provided ────────────
    if voice_text:
        advisory.text += f"\n\n---\n**Farmer's note:** {voice_text}"

    # ── 6. Generate TTS audio ───────────────────────────────────────────
    audio_url = None
    try:
        from gtts import gTTS
        tts = gTTS(text=advisory.text, lang=advisory.language)

        audio_dir = Path(settings.MEDIA_ROOT) / "guest_audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        audio_filename = f"scan_{uuid.uuid4().hex[:10]}_{advisory.language}.mp3"
        audio_path     = audio_dir / audio_filename
        tts.save(str(audio_path))
        audio_url = settings.MEDIA_URL + f"guest_audio/{audio_filename}"
    except Exception as e:
        print(f"Guest TTS failed: {e}")

    # ── 7. Build response ───────────────────────────────────────────────
    payload = {
        "disease":         disease,
        "crop":            crop,
        "confidence":      round(confidence, 4),
        "classifier_mode": classifier_mode,
        "risk_band":       risk_band,
        "risk_score":      round(float(risk_score), 4),
        "advisory_text":   advisory.text,
        "advisory_mode":   advisory.generation_mode,
        "advisory_source": ", ".join(advisory.sources) if advisory.sources else None,
        "audio_url":       audio_url,
        "language":        advisory.language,
    }
    return JsonResponse(payload)
