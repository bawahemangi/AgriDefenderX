"""
Lightweight, dependency-free (no torch needed) image feature extraction.

Used by the demo/fallback classifier (see demo_model.py, infer.py) so the
full pipeline -- upload -> predict -> risk -> advisory -- runs end-to-end
on any machine, even before you've trained and deployed the real CNN from
model.py/train.py.

This is NOT a substitute for the real CNN. It captures coarse color and
texture statistics (how much of the leaf looks brown/yellow/necrotic vs.
uniformly green, roughly how "spotty" the surface texture is) which
correlate loosely with disease presence, but it cannot reliably
distinguish between different diseases the way a properly trained CNN can.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

FEATURE_NAMES = [
    "mean_r", "mean_g", "mean_b",
    "std_r", "std_g", "std_b",
    "green_fraction", "brown_yellow_fraction", "dark_spot_fraction",
    "edge_density",
]


def extract_features(image: Image.Image) -> np.ndarray:
    img = image.convert("RGB").resize((128, 128))
    arr = np.asarray(img).astype(np.float32) / 255.0
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]

    mean_r, mean_g, mean_b = r.mean(), g.mean(), b.mean()
    std_r, std_g, std_b = r.std(), g.std(), b.std()

    # Healthy leaf tissue: green channel clearly dominant.
    green_mask = (g > r * 1.05) & (g > b * 1.05)
    green_fraction = green_mask.mean()

    # Blight/rust/necrotic tissue: brown-yellow hues (R and G both notably
    # above B, R close to or above G).
    brown_yellow_mask = (r > b * 1.15) & (g > b * 1.05) & (r < 0.95)
    brown_yellow_fraction = brown_yellow_mask.mean()

    # Dark lesions / mold: low overall brightness patches.
    brightness = (r + g + b) / 3.0
    dark_spot_mask = brightness < (brightness.mean() * 0.5)
    dark_spot_fraction = dark_spot_mask.mean()

    # Crude texture/edge proxy via finite-difference gradient magnitude.
    gray = brightness
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edge_density = float(gx.mean() + gy.mean())

    return np.array([
        mean_r, mean_g, mean_b,
        std_r, std_g, std_b,
        green_fraction, brown_yellow_fraction, dark_spot_fraction,
        edge_density,
    ], dtype=np.float32)
