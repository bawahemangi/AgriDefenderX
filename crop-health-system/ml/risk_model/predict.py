"""Risk scoring inference wrapper used by the Django backend."""
from __future__ import annotations

import pickle
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
MODEL_PATH = HERE / "risk_model.pkl"

_cache = None


def _load():
    global _cache
    if _cache is None:
        with open(MODEL_PATH, "rb") as f:
            _cache = pickle.load(f)
    return _cache


def risk_band(score: float) -> str:
    if score < 0.30:
        return "LOW"
    elif score < 0.70:
        return "MEDIUM"
    return "HIGH"


def predict_risk(features: dict) -> dict:
    """
    features: dict with keys matching FEATURE_COLUMNS in train_risk_model.py, e.g.
        {
            "temperature_c": 28.0,
            "humidity_pct": 87.0,
            "rainfall_mm_7d": 14.0,
            "wind_kmh": 8.0,
            "days_since_sowing": 55,
            "growth_stage_code": 1,       # 0=veg 1=flowering 2=fruiting 3=maturity
            "pest_trap_count_7d": 12,
            "nearby_confirmed_cases_14d": 3,
            "image_model_confidence": 0.91,
            "image_model_flagged_disease": 1,
        }
    """
    payload = _load()
    model, feature_cols = payload["model"], payload["features"]
    row = pd.DataFrame([{col: features.get(col, 0) for col in feature_cols}])
    score = float(model.predict_proba(row)[0, 1])
    return {"risk_score": round(score, 4), "risk_band": risk_band(score)}


if __name__ == "__main__":
    import json

    sample = {
        "temperature_c": 29,
        "humidity_pct": 88,
        "rainfall_mm_7d": 20,
        "wind_kmh": 6,
        "days_since_sowing": 48,
        "growth_stage_code": 1,
        "pest_trap_count_7d": 15,
        "nearby_confirmed_cases_14d": 4,
        "image_model_confidence": 0.83,
        "image_model_flagged_disease": 1,
    }
    print(json.dumps(predict_risk(sample), indent=2))
