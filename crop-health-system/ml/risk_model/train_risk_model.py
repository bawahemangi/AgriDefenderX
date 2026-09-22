"""
Trains the disease/pest RISK SCORING model.

Unlike the image classifier, this model works on structured/tabular data
(weather, crop stage, pest counts, local disease history, image-model
confidence) -- exactly XGBoost's sweet spot, and exactly what the problem
statement asks for: "weather, crop stage, variety, soil condition and
local pest history ... combined into actionable farm-level alerts."

TRAINING DATA: this script generates synthetic data with agronomically
plausible relationships (e.g. higher humidity + warm temperature raises
fungal risk; higher pest trap counts raise risk; a previous outbreak
nearby raises risk) so the model actually learns a sensible, non-random
decision boundary and the whole pipeline is demoable immediately.

TO GO TO PRODUCTION: replace generate_synthetic_dataset() with real
historical data -- confirmed disease reports (from ExpertReview in the
Django app) joined with the weather and pest data recorded at the time.
The training/inference code (features in, risk score out) does not need
to change, only the data source.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

HERE = Path(__file__).parent

FEATURE_COLUMNS = [
    "temperature_c",
    "humidity_pct",
    "rainfall_mm_7d",
    "wind_kmh",
    "days_since_sowing",
    "growth_stage_code",     # 0=vegetative 1=flowering 2=fruiting 3=maturity
    "pest_trap_count_7d",
    "nearby_confirmed_cases_14d",
    "image_model_confidence",
    "image_model_flagged_disease",   # 1 if classifier predicted non-healthy
]

GROWTH_STAGES = {"vegetative": 0, "flowering": 1, "fruiting": 2, "maturity": 3}


def generate_synthetic_dataset(n: int = 6000, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    temperature_c = rng.normal(28, 5, n).clip(10, 42)
    humidity_pct = rng.normal(65, 18, n).clip(15, 100)
    rainfall_mm_7d = rng.exponential(12, n).clip(0, 150)
    wind_kmh = rng.normal(10, 5, n).clip(0, 40)
    days_since_sowing = rng.integers(5, 140, n)
    growth_stage_code = rng.integers(0, 4, n)
    pest_trap_count_7d = rng.poisson(8, n)
    nearby_confirmed_cases_14d = rng.poisson(2, n)
    image_model_confidence = rng.beta(2, 2, n)
    image_model_flagged_disease = rng.binomial(1, 0.5, n)

    # Latent "true" risk as a plausible agronomic function of the inputs,
    # then a binary/prob outbreak label sampled from it -- this is what
    # gives XGBoost a real, learnable signal rather than pure noise.
    latent = (
        0.06 * (humidity_pct - 50)
        + 0.10 * (temperature_c - 22).clip(0, None)
        + 0.035 * rainfall_mm_7d
        - 0.03 * wind_kmh
        + 0.30 * pest_trap_count_7d
        + 0.55 * nearby_confirmed_cases_14d
        + 3.2 * image_model_flagged_disease * image_model_confidence
        + 1.0 * (growth_stage_code == 1).astype(float)   # flowering = more susceptible
        - 0.015 * np.abs(days_since_sowing - 60)
        + rng.normal(0, 0.9, n)                            # irreducible noise
    )
    prob = 1 / (1 + np.exp(-(latent - latent.mean()) / latent.std()))
    outbreak_confirmed = rng.binomial(1, prob)

    df = pd.DataFrame({
        "temperature_c": temperature_c,
        "humidity_pct": humidity_pct,
        "rainfall_mm_7d": rainfall_mm_7d,
        "wind_kmh": wind_kmh,
        "days_since_sowing": days_since_sowing,
        "growth_stage_code": growth_stage_code,
        "pest_trap_count_7d": pest_trap_count_7d,
        "nearby_confirmed_cases_14d": nearby_confirmed_cases_14d,
        "image_model_confidence": image_model_confidence,
        "image_model_flagged_disease": image_model_flagged_disease,
        "outbreak_confirmed": outbreak_confirmed,
    })
    return df


def main():
    df = generate_synthetic_dataset()
    X, y = df[FEATURE_COLUMNS], df["outbreak_confirmed"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=7, stratify=y
    )

    model = XGBClassifier(
        n_estimators=250,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="auc",
        random_state=7,
    )
    model.fit(X_train, y_train)

    auc = roc_auc_score(y_test, model.predict_proba(X_test)[:, 1])
    print(f"Risk model trained. Held-out AUC on synthetic data: {auc:.3f}")
    print("(This validates the pipeline, not real-world accuracy -- retrain "
          "on real confirmed-case data before relying on it operationally.)")

    importances = pd.Series(model.feature_importances_, index=FEATURE_COLUMNS)
    print("\nFeature importances:")
    print(importances.sort_values(ascending=False).round(3).to_string())

    out_path = HERE / "risk_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({"model": model, "features": FEATURE_COLUMNS}, f)
    print(f"\nSaved: {out_path}")


if __name__ == "__main__":
    main()
