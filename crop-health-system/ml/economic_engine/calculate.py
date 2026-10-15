"""
ml/economic_engine/calculate.py
================================
Agricultural Economic Decision Engine
--------------------------------------
Given a disease scan result + farm context, this module answers:
    "Is it economically worthwhile to treat this crop?"

It computes:
  • expected_yield_value  – what the healthy crop would be worth (₹)
  • current_loss_value    – value already lost to disease before treatment (₹)
  • treatment_cost        – realistic cost to treat the affected area (₹)
  • expected_recovery     – value likely recovered after treatment (₹)
  • net_benefit           – expected_recovery − treatment_cost (₹)
  • roi_pct               – return on treatment investment (%)
  • verdict               – "TREAT" | "ACCEPT_LOSS" | "MONITOR"
  • rationale             – one human-readable sentence

All crop-market-price data is stored below as reasonable Indian-market defaults
(₹/quintal, which is ₹/100 kg).  Farmers can override via the farm's CropCycle
record if we add those fields in future.

NOTE: This module has zero external dependencies (pure Python stdlib) so it
works without any additional pip packages.
"""
from __future__ import annotations

import dataclasses
from typing import Optional

# ---------------------------------------------------------------------------
# Reference data  (₹ per quintal = ₹ per 100 kg)
# ---------------------------------------------------------------------------
# MSP / prevailing market price in INR/quintal (2024–25 estimates).
# Source: India MSP notifications + APMC market aggregators.
CROP_PRICE_PER_QUINTAL: dict[str, float] = {
    "tomato":       1800,
    "potato":       1200,
    "cotton":       7020,   # MSP Kharif 2024
    "wheat":        2275,   # MSP Rabi 2024-25
    "rice":         2300,   # MSP Kharif 2024 (common variety)
    "maize":        2090,
    "sugarcane":     370,   # per quintal
    "soybean":      4892,
    "groundnut":    6783,
    "onion":        1000,
    "chilli":       8000,
    "grape":        4000,
    "mango":        3000,
    "banana":        500,
    "default":      2000,   # fallback
}

# Typical yield in quintals/acre for healthy crop
TYPICAL_YIELD_QUINTALS_ACRE: dict[str, float] = {
    "tomato":      80,
    "potato":      80,
    "cotton":       7,
    "wheat":       15,
    "rice":        20,
    "maize":       18,
    "sugarcane":  400,
    "soybean":     10,
    "groundnut":   12,
    "onion":       50,
    "chilli":      15,
    "grape":       40,
    "mango":       30,
    "banana":     100,
    "default":     15,
}

# Treatment cost per acre in ₹ (fungicide/pesticide + labour).
# Approximate field data from KVK bulletins.
TREATMENT_COST_PER_ACRE: dict[str, float] = {
    "tomato":     3500,
    "potato":     3000,
    "cotton":     5000,
    "wheat":      2500,
    "rice":       3000,
    "maize":      2000,
    "sugarcane":  4000,
    "soybean":    2500,
    "groundnut":  2800,
    "onion":      3200,
    "chilli":     4500,
    "grape":      6000,
    "mango":      3500,
    "banana":     2500,
    "default":    3000,
}

# ---------------------------------------------------------------------------
# Disease → severity factors
# ---------------------------------------------------------------------------
# damage_fraction: fraction of yield already lost if untreated
# recovery_fraction: fraction of remaining yield recoverable with treatment
# treatability: 0..1  how well the disease responds to typical treatment
DISEASE_PROFILES: dict[str, dict] = {
    "early blight":          {"damage": 0.25, "recovery": 0.75, "treatability": 0.80},
    "late blight":           {"damage": 0.45, "recovery": 0.55, "treatability": 0.65},
    "leaf curl":             {"damage": 0.35, "recovery": 0.60, "treatability": 0.55},
    "powdery mildew":        {"damage": 0.20, "recovery": 0.80, "treatability": 0.85},
    "downy mildew":          {"damage": 0.30, "recovery": 0.65, "treatability": 0.70},
    "bacterial wilt":        {"damage": 0.60, "recovery": 0.20, "treatability": 0.25},
    "fusarium wilt":         {"damage": 0.65, "recovery": 0.15, "treatability": 0.20},
    "anthracnose":           {"damage": 0.30, "recovery": 0.70, "treatability": 0.75},
    "rust":                  {"damage": 0.35, "recovery": 0.65, "treatability": 0.70},
    "mosaic virus":          {"damage": 0.50, "recovery": 0.25, "treatability": 0.20},
    "leaf spot":             {"damage": 0.22, "recovery": 0.78, "treatability": 0.80},
    "yellow mosaic virus":   {"damage": 0.55, "recovery": 0.20, "treatability": 0.20},
    "gray leaf spot":        {"damage": 0.28, "recovery": 0.70, "treatability": 0.72},
    "northern leaf blight":  {"damage": 0.32, "recovery": 0.65, "treatability": 0.68},
    "cercospora leaf spot":  {"damage": 0.25, "recovery": 0.72, "treatability": 0.75},
    "black rot":             {"damage": 0.40, "recovery": 0.45, "treatability": 0.50},
    "common rust":           {"damage": 0.28, "recovery": 0.70, "treatability": 0.75},
    "southern leaf blight":  {"damage": 0.38, "recovery": 0.58, "treatability": 0.62},
    "healthy":               {"damage": 0.00, "recovery": 1.00, "treatability": 1.00},
    "default":               {"damage": 0.30, "recovery": 0.60, "treatability": 0.65},
}

# Risk-band multipliers on the damage fraction (HIGH risk → disease spreads faster)
RISK_DAMAGE_MULTIPLIER: dict[str, float] = {
    "LOW":    0.80,
    "MEDIUM": 1.00,
    "HIGH":   1.35,
}


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclasses.dataclass
class EconomicResult:
    # Core numbers (all ₹)
    expected_yield_value: float   # full healthy-crop value
    current_loss_value: float     # value already destroyed
    treatment_cost: float         # cost of one treatment round
    expected_recovery: float      # value that comes back after treatment
    net_benefit: float            # expected_recovery − treatment_cost
    roi_pct: float                # net_benefit / treatment_cost * 100

    # Decision
    verdict: str                  # "TREAT" | "ACCEPT_LOSS" | "MONITOR"
    rationale: str                # plain-English sentence for the farmer

    # Metadata
    crop: str
    disease: str
    area_acres: float
    risk_band: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ---------------------------------------------------------------------------
# Main calculation function
# ---------------------------------------------------------------------------
def calculate_economics(
    crop: str,
    disease: str,
    risk_band: str,
    area_acres: float = 1.0,
    confidence: float = 1.0,
    is_healthy: bool = False,
) -> EconomicResult:
    """
    Returns an EconomicResult with all monetary figures and a verdict.

    Parameters
    ----------
    crop        : e.g. "Tomato" (case-insensitive)
    disease     : e.g. "Early Blight" (case-insensitive)
    risk_band   : "LOW" | "MEDIUM" | "HIGH"
    area_acres  : farm area in acres (defaults to 1 for guest/scan use)
    confidence  : classifier confidence 0..1  (lower → widen uncertainty)
    is_healthy  : if True, short-circuit to a no-action result
    """
    crop_key    = crop.lower().strip()
    disease_key = disease.lower().strip()
    risk_key    = risk_band.upper().strip() if risk_band else "MEDIUM"

    # Resolve lookups (partial match fallback for disease)
    price_per_q = _lookup(CROP_PRICE_PER_QUINTAL, crop_key)
    yield_q     = _lookup(TYPICAL_YIELD_QUINTALS_ACRE, crop_key)
    treat_cost_per_a = _lookup(TREATMENT_COST_PER_ACRE, crop_key)
    profile     = _disease_profile(disease_key)

    # Scale to actual area
    total_yield_value = price_per_q * yield_q * area_acres  # ₹

    # --- Healthy crop short-circuit ---
    # No disease means no loss, no treatment needed, and therefore no
    # expenditure or "profit from treatment" to display. Return zeroed
    # financials immediately to avoid misleading numbers in the UI.
    if is_healthy or profile["damage"] == 0.0:
        return EconomicResult(
            expected_yield_value=round(total_yield_value, 2),
            current_loss_value=0.0,
            treatment_cost=0.0,
            expected_recovery=0.0,
            net_benefit=0.0,
            roi_pct=0.0,
            verdict="MONITOR",
            rationale=(
                "Crop appears healthy. No treatment needed. "
                "Continue standard monitoring practices."
            ),
            crop=crop,
            disease=disease,
            area_acres=area_acres,
            risk_band=risk_key,
        )

    treatment_cost    = treat_cost_per_a * area_acres        # ₹

    # Adjust damage fraction for risk environment
    risk_mult     = RISK_DAMAGE_MULTIPLIER.get(risk_key, 1.0)
    damage_frac   = min(profile["damage"] * risk_mult, 0.95)

    # Confidence adjustment — low confidence → be more conservative (less certain about damage)
    # We shrink damage a bit if confidence is low (model might be wrong)
    damage_frac = damage_frac * (0.6 + 0.4 * confidence)

    current_loss  = total_yield_value * damage_frac
    # Value remaining in the field that could still be recovered
    salvageable   = total_yield_value - current_loss
    expected_recovery = salvageable * profile["recovery"] * profile["treatability"]
    net_benefit   = expected_recovery - treatment_cost
    roi_pct       = (net_benefit / treatment_cost * 100) if treatment_cost > 0 else 0.0

    # --- Verdict logic (only reached for diseased crops) ---
    if False:  # placeholder; healthy crops already returned above
        verdict   = "MONITOR"
        rationale = ""
    elif profile["treatability"] < 0.30:
        verdict   = "ACCEPT_LOSS"
        rationale = (
            f"Detected {disease} has very low treatment response. "
            f"Expected recovery of ₹{expected_recovery:,.0f} does not justify "
            f"the treatment expenditure of ₹{treatment_cost:,.0f}. "
            "Focus on removing affected plants and preventing further spread."
        )
    elif net_benefit <= 0:
        verdict   = "ACCEPT_LOSS"
        rationale = (
            f"Treatment cost (₹{treatment_cost:,.0f}) exceeds expected recovery "
            f"(₹{expected_recovery:,.0f}). Avoid unnecessary expenditure. "
            "Salvage what you can and plan better disease management next cycle."
        )
    elif roi_pct > 150:
        verdict   = "TREAT"
        rationale = (
            f"Intervention is strongly economically justified. "
            f"₹{treatment_cost:,.0f} treatment is expected to recover ₹{expected_recovery:,.0f} "
            f"(ROI {roi_pct:.0f}%). Act immediately."
        )
    elif roi_pct > 30:
        verdict   = "TREAT"
        rationale = (
            f"Intervention is economically worthwhile. "
            f"Expected recovery (₹{expected_recovery:,.0f}) exceeds treatment cost "
            f"(₹{treatment_cost:,.0f}) with a {roi_pct:.0f}% return."
        )
    else:
        verdict   = "MONITOR"
        rationale = (
            f"Marginal economic case (ROI {roi_pct:.0f}%). Treatment might barely break even. "
            "Monitor closely for 48–72 hours; treat only if symptoms worsen."
        )

    return EconomicResult(
        expected_yield_value=round(total_yield_value, 2),
        current_loss_value=round(current_loss, 2),
        treatment_cost=round(treatment_cost, 2),
        expected_recovery=round(expected_recovery, 2),
        net_benefit=round(net_benefit, 2),
        roi_pct=round(roi_pct, 1),
        verdict=verdict,
        rationale=rationale,
        crop=crop,
        disease=disease,
        area_acres=area_acres,
        risk_band=risk_key,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _lookup(table: dict, key: str) -> float:
    """Case-insensitive lookup with partial-match fallback."""
    if key in table:
        return table[key]
    for k, v in table.items():
        if k in key or key in k:
            return v
    return table["default"]


def _disease_profile(disease_key: str) -> dict:
    """Resolve disease profile with partial-match fallback."""
    if disease_key in DISEASE_PROFILES:
        return DISEASE_PROFILES[disease_key]
    for k, v in DISEASE_PROFILES.items():
        if k in disease_key or disease_key in k:
            return v
    return DISEASE_PROFILES["default"]
