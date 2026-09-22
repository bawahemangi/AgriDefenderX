"""
Trains the DEMO fallback classifier (ml/disease_classifier/demo_feature_model.pkl).

This is NOT the real disease classifier -- it's a small RandomForest over
coarse color/texture statistics (features.py), trained on synthetically
generated proxy data so that the full application pipeline (upload photo
-> prediction -> risk score -> advisory) runs and can be demoed end-to-end
before you've trained the real CNN on actual labeled photos (model.py +
train.py, using PlantVillage or your own dataset).

Each of the 38 classes is assigned a rough visual archetype (healthy /
blight-and-spot / mildew-and-mold / rust-and-rot / virus-and-curl) based on
its name, and synthetic feature vectors are sampled around a centroid for
that archetype. This gives the demo classifier *some* structure to learn
(e.g. it will reliably call a mostly-green, low-texture photo "healthy",
and a browning, spotty photo something in the blight family) without
pretending to distinguish between, say, Tomato Early Blight and Potato
Early Blight from color statistics alone -- a real CNN is what makes that
distinction possible, this is only meant to make the rest of the system
demoable in its absence.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.ensemble import RandomForestClassifier

HERE = Path(__file__).parent

ARCHETYPES = {
    # name substring -> (mean_r, mean_g, mean_b, std_r, std_g, std_b,
    #                     green_fraction, brown_yellow_fraction, dark_spot_fraction, edge_density)
    "healthy":       (0.35, 0.55, 0.25, 0.08, 0.08, 0.06, 0.75, 0.05, 0.03, 0.015),
    "blight":        (0.45, 0.42, 0.20, 0.12, 0.11, 0.08, 0.35, 0.45, 0.15, 0.035),
    "spot":          (0.42, 0.45, 0.22, 0.12, 0.11, 0.08, 0.40, 0.38, 0.18, 0.040),
    "rust":          (0.50, 0.38, 0.18, 0.13, 0.10, 0.07, 0.28, 0.52, 0.10, 0.030),
    "rot":           (0.30, 0.30, 0.20, 0.14, 0.13, 0.10, 0.25, 0.30, 0.35, 0.045),
    "mildew":        (0.55, 0.58, 0.50, 0.09, 0.09, 0.09, 0.40, 0.15, 0.05, 0.050),
    "mold":          (0.40, 0.42, 0.30, 0.11, 0.10, 0.09, 0.38, 0.25, 0.20, 0.055),
    "mosaic":        (0.38, 0.48, 0.28, 0.15, 0.16, 0.10, 0.45, 0.20, 0.08, 0.060),
    "curl":          (0.36, 0.46, 0.26, 0.14, 0.15, 0.09, 0.42, 0.22, 0.08, 0.055),
    "greening":      (0.42, 0.44, 0.24, 0.13, 0.12, 0.09, 0.38, 0.30, 0.10, 0.040),
    "scab":          (0.40, 0.40, 0.22, 0.13, 0.12, 0.09, 0.35, 0.35, 0.20, 0.042),
    "spider_mites":  (0.44, 0.46, 0.24, 0.14, 0.13, 0.09, 0.36, 0.28, 0.12, 0.048),
}

DEFAULT_ARCHETYPE = "blight"


def archetype_for(class_name: str) -> str:
    lower = class_name.lower()
    for key in ARCHETYPES:
        if key in lower:
            return key
    if "healthy" in lower:
        return "healthy"
    return DEFAULT_ARCHETYPE


def main(samples_per_class: int = 150, seed: int = 42):
    rng = np.random.default_rng(seed)

    with open(HERE / "labels.json") as f:
        classes = json.load(f)["classes"]

    X, y = [], []
    for class_name in classes:
        archetype = archetype_for(class_name)
        centroid = np.array(ARCHETYPES[archetype])
        for _ in range(samples_per_class):
            noise = rng.normal(0, 0.05, size=centroid.shape)
            sample = np.clip(centroid + noise, 0.0, 1.0)
            X.append(sample)
            y.append(class_name)

    X = np.array(X, dtype=np.float32)
    y = np.array(y)

    clf = RandomForestClassifier(
        n_estimators=200, max_depth=8, random_state=seed, n_jobs=-1
    )
    clf.fit(X, y)

    train_acc = clf.score(X, y)
    print(f"Demo feature-classifier trained on synthetic proxy data. "
          f"Train accuracy (on synthetic data, NOT a real metric): {train_acc:.3f}")

    out_path = HERE / "demo_feature_model.pkl"
    with open(out_path, "wb") as f:
        pickle.dump({"model": clf, "classes": classes}, f)
    print(f"Saved: {out_path}")


if __name__ == "__main__":
    main()
