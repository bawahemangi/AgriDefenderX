"""
reports/apps.py
---------------
Django AppConfig for the reports app.

On startup (ready()) we pre-warm the two heaviest ML assets in a
background daemon thread so the very first farmer scan request is fast:

  • The ONNX inference session (EfficientNetV2-S, ~80 MB) – loading it
    from disk + initialising onnxruntime takes 2-6 s on a CPU-only box.
  • The TF-IDF advisory retriever (fits in memory in < 1 s, but
    building the TF-IDF matrix on the first request adds latency).

Because Django's ready() is called before the first request arrives
the warm-up is transparent to users.  If either asset fails to load
(missing files, import error) we catch the exception and let the
normal fallback paths handle it at request time – the app still works,
just slower on the first call.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from django.apps import AppConfig


class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "reports"

    def ready(self) -> None:  # noqa: D401
        """Pre-warm ML models in a background thread so request #1 is fast."""
        t = threading.Thread(target=_warmup, daemon=True, name="ml-warmup")
        t.start()


# ---------------------------------------------------------------------------
# Warm-up routine (runs in background thread)
# ---------------------------------------------------------------------------

def _warmup() -> None:
    BASE_DIR = Path(__file__).resolve().parent.parent
    for sub in ("disease_classifier", "risk_model", "advisory_rag", "economic_engine"):
        p = str(BASE_DIR / "ml" / sub)
        if p not in sys.path:
            sys.path.insert(0, p)

    # 1. ONNX classifier (the heavy one)
    try:
        import infer as classifier_infer  # noqa: F401
        classifier_infer._load_onnx()  # pulls the session into the module-level cache
        print("[warmup] ONNX classifier loaded.")
    except Exception as exc:
        print(f"[warmup] ONNX classifier skipped: {exc}")

    # 2. Risk model
    try:
        import predict as risk_predict  # noqa: F401
        risk_predict._load()
        print("[warmup] Risk model loaded.")
    except Exception as exc:
        print(f"[warmup] Risk model skipped: {exc}")

    # 3. Advisory RAG retriever (builds TF-IDF matrix)
    try:
        from retriever import get_retriever
        get_retriever()
        print("[warmup] Advisory retriever loaded.")
    except Exception as exc:
        print(f"[warmup] Advisory retriever skipped: {exc}")
