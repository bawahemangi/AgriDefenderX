"""
Single entry point the Django backend calls for disease/pest classification.

classify_image(path_or_pil_image) -> dict:
    {
        "predicted_class": "Tomato___Early_blight",
        "crop": "Tomato",
        "disease": "Early blight",
        "confidence": 0.83,
        "top_k": [("Tomato___Early_blight", 0.83), ...],
        "mode": "cnn" | "demo_heuristic",
    }

Resolution order:
    1. If a trained checkpoint exists at CHECKPOINT_PATH and torch is
       importable -> real CNN inference (model.py).
    2. Otherwise -> demo_feature_model.pkl heuristic fallback (features.py +
       train_demo_model.py), so the app still runs end-to-end without a
       trained checkpoint. The result is clearly tagged mode="demo_heuristic"
       so the rest of the pipeline (e.g. the expert-review threshold) can
       treat it with appropriately lower trust.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Union

from PIL import Image

HERE = Path(__file__).parent
CHECKPOINT_PATH = HERE / "checkpoints" / "disease_classifier.pt"
DEMO_MODEL_PATH = HERE / "demo_feature_model.pkl"

_cnn_cache = None
_demo_cache = None


def _split_class_name(class_name: str) -> tuple[str, str]:
    if "___" in class_name:
        crop, disease = class_name.split("___", 1)
    else:
        crop, disease = "Unknown", class_name
    return crop.replace("_", " "), disease.replace("_", " ")


def _load_cnn():
    global _cnn_cache
    if _cnn_cache is not None:
        return _cnn_cache
    import torch
    from model import LeafNet, build_efficientnet, input_size
    from torchvision import transforms

    ckpt = torch.load(CHECKPOINT_PATH, map_location="cpu")
    classes = ckpt["classes"]
    arch = ckpt.get("arch", "efficientnet")
    model = (LeafNet(len(classes)) if arch == "leafnet"
             else build_efficientnet(len(classes), pretrained=False))
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    tf = transforms.Compose([
        transforms.Resize(input_size()),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    _cnn_cache = (model, classes, tf, torch)
    return _cnn_cache


def _load_demo():
    global _demo_cache
    if _demo_cache is not None:
        return _demo_cache
    with open(DEMO_MODEL_PATH, "rb") as f:
        payload = pickle.load(f)
    _demo_cache = payload
    return _demo_cache


def _cnn_available() -> bool:
    if not CHECKPOINT_PATH.exists():
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def classify_image(image: Union[str, Path, Image.Image], top_k: int = 3) -> dict:
    if isinstance(image, (str, Path)):
        image = Image.open(image)

    if _cnn_available():
        model, classes, tf, torch = _load_cnn()
        with torch.no_grad():
            x = tf(image.convert("RGB")).unsqueeze(0)
            probs = torch.softmax(model(x), dim=1)[0]
        order = torch.argsort(probs, descending=True)[:top_k]
        top = [(classes[i], float(probs[i])) for i in order]
        mode = "cnn"
    else:
        from features import extract_features
        payload = _load_demo()
        clf, classes = payload["model"], payload["classes"]
        feats = extract_features(image).reshape(1, -1)
        probs = clf.predict_proba(feats)[0]
        order = probs.argsort()[::-1][:top_k]
        top = [(clf.classes_[i], float(probs[i])) for i in order]
        mode = "demo_heuristic"

    predicted_class, confidence = top[0]
    crop, disease = _split_class_name(predicted_class)

    return {
        "predicted_class": predicted_class,
        "crop": crop,
        "disease": disease,
        "confidence": round(confidence, 4),
        "top_k": [(c, round(p, 4)) for c, p in top],
        "mode": mode,
    }


if __name__ == "__main__":
    import sys
    import numpy as np

    if len(sys.argv) > 1:
        result = classify_image(sys.argv[1])
    else:
        # No sample image given -- synthesize one so this still runs as a
        # smoke test with zero external inputs.
        rng = np.random.default_rng(0)
        arr = (rng.integers(60, 180, size=(128, 128, 3))).astype("uint8")
        arr[:, :, 1] = np.clip(arr[:, :, 1] + 40, 0, 255)  # push it greenish
        result = classify_image(Image.fromarray(arr))

    print(json.dumps(result, indent=2))
