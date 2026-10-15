"""
Guest scan view — runs the full ML pipeline (image classify + risk + advisory)
without requiring the user to be logged in or have a farm record.

Performance optimisations
--------------------------
1. PARALLEL risk + economics
   Risk scoring and economic engine run concurrently via ThreadPoolExecutor.

2. FIRE-AND-FORGET TTS
   gTTS is slow (2–5 s network call).  We return the scan result
   immediately with audio_url=null and kick off a daemon thread.
   Frontend polls GET /scan/audio/<scan_id>/ until the file exists.

3. FIRE-AND-FORGET TRANSLATION
   MyMemory / Google Translate can take 5–25 s on a cold cache.
   Strategy:
     a) English advisory is returned INSTANTLY (pure template, 0 network calls).
     b) If the user's language is non-English AND the translation was
        previously cached → serve the translated version immediately.
     c) If not cached → return English with translation_pending=true and
        trigger a background daemon thread to translate.
     d) Frontend polls GET /scan/translation/<scan_id>/ every 3 s until
        the translation is ready, then swaps the advisory text in-place.

4. IN-PROCESS CACHES
   _cached_advisory_en   — English template results (LRU, maxsize=256)
   generate._translation_cache — translated results (persists for process life)
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST


# ── Make ml subpackages importable ─────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
for _sub in ("disease_classifier", "risk_model", "advisory_rag", "economic_engine"):
    _p = str(BASE_DIR / "ml" / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ── Shared thread-pool (reused across requests) ────────────────────────────
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix="scan-worker")

# ── In-flight translation jobs: scan_id → {done, text, language, mode} ────
_translation_jobs: dict[str, dict] = {}
_translation_lock = threading.Lock()


# ===========================================================================
# Public views
# ===========================================================================

def scan_page(request):
    """Renders the public crop-scan landing page."""
    return render(request, "farmer/scan.html")


def audio_status(request, scan_id: str):
    """
    Poll endpoint: returns {"ready": true, "audio_url": "..."} once gTTS
    has finished writing the file.
    """
    lang = request.GET.get("lang", "en")
    filename = f"scan_{scan_id}_{lang}.mp3"
    audio_path = Path(settings.MEDIA_ROOT) / "guest_audio" / filename
    if audio_path.exists():
        return JsonResponse({
            "ready": True,
            "audio_url": settings.MEDIA_URL + f"guest_audio/{filename}",
        })
    return JsonResponse({"ready": False})


def translation_status(request, scan_id: str):
    """
    Poll endpoint: returns {"ready": true, "advisory_text": "...",
    "advisory_mode": "...", "language": "..."} once the background
    translation thread has finished.
    """
    with _translation_lock:
        job = _translation_jobs.get(scan_id)

    if job and job.get("done"):
        return JsonResponse({
            "ready":         True,
            "advisory_text": job["text"],
            "advisory_mode": job["mode"],
            "language":      job["language"],
        })
    return JsonResponse({"ready": False})


@require_POST
def analyse_image(request):
    """
    AJAX endpoint called by the scan page.
    Accepts : image (file), language (str), voice_text (str, optional)
    Returns : JSON — disease, crop, risk, advisory (English or cached
              translation), economics, scan_id.
              audio_url is always null on return; poll /scan/audio/<id>/.
              If translation is pending, translation_pending=true and
              frontend polls /scan/translation/<id>/.
    """
    image_file = request.FILES.get("image")
    session_lang = request.session.get("_language", request.LANGUAGE_CODE or "en")
    language = request.POST.get("language") or session_lang
    if language not in ("en", "mr", "hi"):
        language = "en"
    voice_text = request.POST.get("voice_text", "").strip()

    if not image_file:
        return JsonResponse({"error": "No image provided."}, status=400)

    # ── 1. Save upload to temp file ────────────────────────────────────
    suffix = Path(image_file.name).suffix or ".jpg"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        os.close(fd)
        with open(tmp_path, "wb") as f:
            for chunk in image_file.chunks():
                f.write(chunk)

        # ── 2. Image classification ────────────────────────────────────
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
    low_conf        = confidence < getattr(settings, "LOW_CONFIDENCE_THRESHOLD", 0.20)

    # ── 3. Risk model ──────────────────────────────────────────────────
    def _run_risk():
        import predict as risk_predict
        return risk_predict.predict_risk({
            "temperature_c":              28.0,
            "humidity_pct":               70.0,
            "rainfall_mm_7d":             20.0,
            "wind_kmh":                   12.0,
            "days_since_sowing":          45,
            "growth_stage_code":          2,
            "pest_trap_count_7d":         0,
            "nearby_confirmed_cases_14d": 0,
            "image_model_confidence":     confidence,
            "image_model_flagged_disease": 0 if is_healthy else 1,
        })

    def _run_economics(risk_band_val: str):
        try:
            from calculate import calculate_economics
            econ = calculate_economics(
                crop=crop, disease=disease, risk_band=risk_band_val,
                area_acres=1.0, confidence=confidence, is_healthy=is_healthy,
            )
            return econ.to_dict()
        except Exception as exc:
            print(f"[scan] Economic engine failed: {exc}")
            return None

    risk_future = _POOL.submit(_run_risk)
    risk        = risk_future.result()
    risk_score  = risk["risk_score"]
    risk_band   = risk["risk_band"]

    # Economics runs while we sort out advisory ─────────────────────────
    econ_future = _POOL.submit(_run_economics, risk_band)

    # ── 4. Advisory — English always instant, translate async ──────────
    scan_id = uuid.uuid4().hex[:12]

    # Always fetch English template (fast — pure in-memory lookup)
    en_advisory = _cached_advisory_en(crop, disease, risk_band, low_conf)
    en_text     = en_advisory["text"]
    sources     = en_advisory["sources"]
    en_mode     = en_advisory["generation_mode"]

    translation_pending = False
    advisory_text       = en_text
    advisory_language   = language if language == "en" else "en"  # start English
    advisory_mode       = en_mode

    if language != "en":
        # Check if translation is already cached in generate._translation_cache
        import generate as advisory_generate
        cache_key = (en_text, language)
        cached_tr = advisory_generate._translation_cache.get(cache_key)

        if cached_tr:
            # Warm cache hit — serve translated text immediately
            advisory_text     = cached_tr["text"]
            advisory_language = language
            advisory_mode     = cached_tr["mode"]
        else:
            # Cold — serve English now, translate in background
            translation_pending = True

            def _translate_worker(sid: str, txt: str, lang: str, src_mode: str):
                import generate as ag
                from generate import Advisory, _translate_fallback
                adv = Advisory(
                    disease_title=disease, risk_band=risk_band,
                    actions=[], safe_input_use="", referral_note="",
                    sources=sources, language="en", text=txt,
                    generation_mode=src_mode,
                )
                _translate_fallback(adv, lang)
                with _translation_lock:
                    _translation_jobs[sid] = {
                        "done":     True,
                        "text":     adv.text,
                        "language": adv.language,
                        "mode":     adv.generation_mode,
                    }
                print(f"[scan] Background translation done for {sid} "
                      f"({adv.generation_mode}, lang={adv.language})")

            with _translation_lock:
                _translation_jobs[scan_id] = {"done": False}

            threading.Thread(
                target=_translate_worker,
                args=(scan_id, en_text, language, en_mode),
                daemon=True,
                name=f"translate-{scan_id}",
            ).start()

    # Append voice note
    if voice_text:
        advisory_text += f"\n\n---\n**Farmer's note:** {voice_text}"

    # ── 5. Fire-and-forget TTS ─────────────────────────────────────────
    # TTS lang: use target language if we already have translated text,
    # otherwise 'en' for now (audio will update when frontend polls).
    tts_lang      = advisory_language   # 'en' if pending, else target lang
    audio_dir     = Path(settings.MEDIA_ROOT) / "guest_audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_filename = f"scan_{scan_id}_{tts_lang}.mp3"
    audio_path     = audio_dir / audio_filename

    def _tts_worker():
        try:
            from gtts import gTTS
            gTTS(text=advisory_text, lang=tts_lang).save(str(audio_path))
        except Exception as exc:
            print(f"[scan] TTS failed: {exc}")

    threading.Thread(target=_tts_worker, daemon=True,
                     name=f"tts-{scan_id}").start()

    econ_data = econ_future.result()

    # ── 6b. Range-based economic estimate (reports/economics.py) ────────
    range_estimate = None
    try:
        from reports.economics import (
            estimate_decision,
            severity_from_risk_band,
            _CROP_PARAMS,
            _lookup_dict as _econ_lookup,
        )
        crop_key = crop.lower().strip()
        crop_defaults = _econ_lookup(_CROP_PARAMS, crop_key)
        severity = severity_from_risk_band(risk_band)
        range_estimate = estimate_decision(
            crop=crop,
            disease=disease,
            severity=severity,
            area_acres=1.0,
            yield_per_acre=crop_defaults.get("yield_per_acre", 15),
            price_per_unit=crop_defaults.get("price_per_unit", 20.0),
            confidence=confidence,
        )
    except Exception as exc:
        print(f"[scan] Range-based economic estimate failed: {exc}")

    # ── 7. Build response ──────────────────────────────────────────────
    payload = {
        "disease":              disease,
        "crop":                 crop,
        "confidence":           round(confidence, 4),
        "classifier_mode":      classifier_mode,
        "risk_band":            risk_band,
        "risk_score":           round(float(risk_score), 4),
        "advisory_text":        advisory_text,
        "advisory_mode":        advisory_mode,
        "advisory_source":      ", ".join(sources) if sources else None,
        "language":             advisory_language,
        "economics":            econ_data,
        "economic_estimate":    range_estimate,
        "audio_url":            None,
        "scan_id":              scan_id,
        "audio_poll_lang":      tts_lang,
        # translation polling
        "translation_pending":  translation_pending,
        "translation_target":   language if translation_pending else None,
    }
    return JsonResponse(payload)


# ===========================================================================
# Caches
# ===========================================================================

@lru_cache(maxsize=256)
def _cached_advisory_en(crop: str, disease: str, risk_band: str,
                         low_confidence: bool) -> dict:
    """
    Returns the English advisory dict (template mode — zero network calls).
    Cached per (crop, disease, risk_band, low_confidence).
    """
    import generate as advisory_generate
    adv = advisory_generate.generate_advisory(
        crop=crop, disease=disease, growth_stage="",
        risk_band=risk_band, language="en", low_confidence=low_confidence,
    )
    return {
        "text":            adv.text,
        "language":        adv.language,
        "generation_mode": adv.generation_mode,
        "sources":         adv.sources,
    }
