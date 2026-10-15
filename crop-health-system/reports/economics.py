"""
reports/economics.py
====================
Pure-Python economic decision helper for the "Treat or Accept the Loss?"
card shown after a disease is detected.

IMPORTANT — PROTOTYPE ASSUMPTIONS
All monetary values (yield, price, loss fractions, treatment efficacy and
treatment costs) come from reports/economics_data.json, which contains
clearly labelled PLACEHOLDER figures assembled from publicly available
MSP notifications, KVK bulletins and APMC market aggregators (2024-25).
These are NOT measured field data.  Replace every value in that file with
extension-office or peer-reviewed research figures before production use.

No ML model is used — this is pure arithmetic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Load reference data once at import time
# ---------------------------------------------------------------------------
_DATA_PATH = Path(__file__).resolve().parent / "economics_data.json"

with open(_DATA_PATH, encoding="utf-8") as _fh:
    _DATA: dict = json.load(_fh)

_CROP_PARAMS: dict       = _DATA["default_crop_params"]
_LOSS_FRAC: dict         = _DATA["loss_fraction"]
_EFFICACY: dict          = _DATA["treatment_efficacy"]
_COST_PER_ACRE: dict     = _DATA["cost_per_acre"]

# +/- range multiplier applied around the central estimate
_RANGE_FACTOR = 0.20   # 20%

# Severity bands we map risk_band → severity key
_SEVERITY_MAP = {
    "LOW":    "low",
    "MEDIUM": "medium",
    "HIGH":   "high",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def estimate_decision(
    crop: str,
    disease: str,
    severity: str,                # "low" | "medium" | "high"   (from risk_band)
    area_acres: float,
    yield_per_acre: float,        # quintals/acre
    price_per_unit: float,        # INR per quintal
    confidence: float,            # 0..1  classifier confidence
    *,
    low_confidence_threshold: float = 0.20,
) -> Optional[dict]:
    """
    Return an economic decision dict, or None if inputs are insufficient
    (area_acres ≤ 0 or disease is healthy).

    Returned dict keys
    ------------------
    expected_value         float   – healthy-crop value (₹), central
    expected_loss_low      float   – loss without treatment, low estimate
    expected_loss_high     float   – loss without treatment, high estimate
    loss_avoided_low       float   – loss avoided by treating, low estimate
    loss_avoided_high      float   – loss avoided by treating, high estimate
    treatment_cost         float   – treatment cost (₹)
    net_benefit_low        float   – net benefit, pessimistic
    net_benefit_high       float   – net benefit, optimistic
    decision_code          str     – "TREAT" | "ACCEPT_LOSS" | "NO_CARD"
    decision_message       str     – plain-language sentence
    is_preliminary         bool    – True when confidence < threshold
    assumptions_used       dict    – echoes the key assumptions applied
    """
    # Normalise
    crop_key    = (crop or "").lower().strip()
    disease_key = (disease or "").lower().strip()
    severity    = (severity or "medium").lower().strip()

    # Healthy crop → no economic card
    if not disease_key or "healthy" in disease_key:
        return None

    # Guard: need area
    if not area_acres or area_acres <= 0:
        return None

    # Validate severity
    if severity not in ("low", "medium", "high"):
        severity = "medium"

    # -- Lookup tables (partial-match fallback → _generic) --
    crop_params     = _lookup_dict(_CROP_PARAMS, crop_key)
    loss_frac_row   = _lookup_dict(_LOSS_FRAC, disease_key)
    efficacy_row    = _lookup_dict(_EFFICACY, disease_key)
    cost_per_acre_v = _lookup_scalar(_COST_PER_ACRE, disease_key)

    loss_frac  = loss_frac_row[severity]
    efficacy   = efficacy_row[severity]

    # -- Central estimates --
    expected_value = area_acres * yield_per_acre * price_per_unit
    expected_loss  = expected_value * loss_frac
    loss_avoided   = expected_loss * efficacy
    treatment_cost = area_acres * cost_per_acre_v
    net_benefit    = loss_avoided - treatment_cost

    # -- ±20% ranges --
    el_lo, el_hi = _range(expected_loss)
    la_lo, la_hi = _range(loss_avoided)
    nb_lo        = la_lo - treatment_cost
    nb_hi        = la_hi - treatment_cost

    # -- Decision --
    is_preliminary = confidence < low_confidence_threshold

    # Low treatability diseases (wilt, virus) → ACCEPT_LOSS even if math says positive
    _low_treat_keywords = ("wilt", "virus", "mosaic")
    low_treatability = any(kw in disease_key for kw in _low_treat_keywords)

    if low_treatability and efficacy < 0.30:
        decision_code    = "ACCEPT_LOSS"
        decision_message = (
            "Severe damage and low recovery potential. "
            "Avoid unnecessary treatment spending; consult your extension officer."
        )
    elif nb_hi <= 0:
        # Even the optimistic scenario is not profitable
        decision_code    = "ACCEPT_LOSS"
        decision_message = (
            "Severe damage and low recovery potential. "
            "Avoid unnecessary treatment spending; consult your extension officer."
        )
    elif net_benefit > 0:
        decision_code    = "TREAT"
        decision_message = "Treatment is economically worthwhile."
    else:
        # net_benefit ≤ 0 but nb_hi > 0 → borderline
        decision_code    = "ACCEPT_LOSS"
        decision_message = (
            "Severe damage and low recovery potential. "
            "Avoid unnecessary treatment spending; consult your extension officer."
        )

    return {
        "expected_value":     round(expected_value, 2),
        "expected_loss_low":  round(el_lo, 2),
        "expected_loss_high": round(el_hi, 2),
        "loss_avoided_low":   round(la_lo, 2),
        "loss_avoided_high":  round(la_hi, 2),
        "treatment_cost":     round(treatment_cost, 2),
        "net_benefit_low":    round(nb_lo, 2),
        "net_benefit_high":   round(nb_hi, 2),
        "decision_code":      decision_code,
        "decision_message":   decision_message,
        "is_preliminary":     is_preliminary,
        "assumptions_used": {
            "crop":           crop_key,
            "disease":        disease_key,
            "severity":       severity,
            "yield_per_acre": yield_per_acre,
            "price_per_unit": price_per_unit,
            "area_acres":     area_acres,
            "loss_fraction":  loss_frac,
            "efficacy":       efficacy,
            "cost_per_acre":  cost_per_acre_v,
            "confidence":     round(confidence, 4),
        },
    }


def severity_from_risk_band(risk_band: str) -> str:
    """Map DiseaseReport.risk_band ('LOW'/'MEDIUM'/'HIGH') → severity key."""
    return _SEVERITY_MAP.get((risk_band or "MEDIUM").upper(), "medium")


# ---------------------------------------------------------------------------
# Optional: lightweight Agmarknet price fetch
# ---------------------------------------------------------------------------

def fetch_mandi_price(crop: str, state: str = "Maharashtra") -> Optional[float]:
    """
    Optionally fetch today's mandi modal price (INR/quintal) from the
    Government of India data.gov.in Agmarknet dataset.

    Requires env var DATA_GOV_API_KEY.  Fully optional — returns None on
    any error (missing key, network timeout, unexpected response shape).
    Never raises.
    """
    api_key = os.environ.get("DATA_GOV_API_KEY", "")
    if not api_key:
        return None

    try:
        import urllib.request
        import urllib.parse

        base = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
        params = urllib.parse.urlencode({
            "api-key":    api_key,
            "format":     "json",
            "limit":      "5",
            "filters[State]":    state,
            "filters[Commodity]": crop.title(),
        })
        url = f"{base}?{params}"

        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        records = data.get("records", [])
        if not records:
            return None

        prices = [
            float(r["Modal_Price"])
            for r in records
            if r.get("Modal_Price") not in (None, "", "0")
        ]
        return round(sum(prices) / len(prices), 2) if prices else None

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lookup_dict(table: dict, key: str) -> dict:
    """Return table[key] or table['_generic'], with partial-match fallback."""
    if key in table:
        return table[key]
    for k, v in table.items():
        if k.startswith("_"):
            continue
        if k in key or key in k:
            return v
    return table.get("_generic", {})


def _lookup_scalar(table: dict, key: str) -> float:
    """Return scalar value from table, with partial-match fallback."""
    if key in table:
        return float(table[key])
    for k, v in table.items():
        if k.startswith("_"):
            continue
        if k in key or key in k:
            return float(v)
    return float(table.get("_generic", 2500))


def _range(value: float) -> tuple[float, float]:
    """Return (low, high) = value ± _RANGE_FACTOR."""
    return value * (1 - _RANGE_FACTOR), value * (1 + _RANGE_FACTOR)
