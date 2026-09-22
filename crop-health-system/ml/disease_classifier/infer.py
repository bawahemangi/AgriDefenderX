"""
Single entry point the Django backend calls for disease/pest classification.

classify_image(path_or_pil_image) -> dict:
    {
        "predicted_class": "Tomato___Early_blight",
        "crop": "Tomato",
        "disease": "Early blight",
        "confidence": 0.83,
        "top_k": [("Tomato___Early_blight", 0.83), ...],
        "mode": "onnx_hf" | "cnn" | "demo_heuristic",
    }

Resolution order (best to fallback):
    1. ONNX model from HuggingFace (BiernyVR/crop-disease-classifier) via onnxruntime
       -- EfficientNetV2-S, 38 classes, 99.98% val accuracy. This is the primary path.
       -- Requires: onnxruntime, disease_model/ folder with .onnx + .onnx.data + classes.json
    2. PyTorch CNN checkpoint (model.py) -- if torch is importable and checkpoint exists.
    3. Demo heuristic fallback (features.py + demo_feature_model.pkl) -- always works,
       clearly tagged mode="demo_heuristic" for lower-trust downstream handling.
"""
from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Union

import numpy as np
from PIL import Image

HERE = Path(__file__).parent

# HuggingFace ONNX model paths (downloaded via download_model.py)
ONNX_MODEL_DIR = HERE.parent.parent / "disease_model"
ONNX_MODEL_PATH = ONNX_MODEL_DIR / "efficientnet_v2_s_best.onnx"
ONNX_CLASSES_PATH = ONNX_MODEL_DIR / "classes.json"

# PyTorch CNN checkpoint (trained manually via train.py)
CHECKPOINT_PATH = HERE / "checkpoints" / "disease_classifier.pt"

# Demo heuristic model
DEMO_MODEL_PATH = HERE / "demo_feature_model.pkl"

_onnx_cache = None
_cnn_cache = None
_demo_cache = None


# ---------------------------------------------------------------------------
# Path 1: ONNX (HuggingFace EfficientNetV2-S — primary path)
# ---------------------------------------------------------------------------

def _onnx_available() -> bool:
    if not ONNX_MODEL_PATH.exists():
        return False
    try:
        import onnxruntime  # noqa: F401
        return True
    except ImportError:
        return False


def _load_onnx():
    global _onnx_cache
    if _onnx_cache is not None:
        return _onnx_cache

    import onnxruntime as ort

    with open(ONNX_CLASSES_PATH) as f:
        meta = json.load(f)

    classes = meta["classes"]
    mean = np.array(meta["normalisation"]["mean"], dtype=np.float32)
    std = np.array(meta["normalisation"]["std"], dtype=np.float32)
    image_size = meta.get("image_size", 224)

    # Use CPU provider; add CUDAExecutionProvider first if GPU is available
    providers = ["CPUExecutionProvider"]
    try:
        import onnxruntime as ort2
        if "CUDAExecutionProvider" in ort2.get_available_providers():
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    except Exception:
        pass

    sess = ort.InferenceSession(str(ONNX_MODEL_PATH), providers=providers)
    input_name = sess.get_inputs()[0].name

    _onnx_cache = (sess, input_name, classes, mean, std, image_size)
    return _onnx_cache


def _preprocess_for_onnx(image: Image.Image, image_size: int,
                          mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Resize → RGB → normalize → NCHW float32."""
    img = image.convert("RGB").resize((image_size, image_size), Image.BILINEAR)
    arr = np.array(img, dtype=np.float32) / 255.0          # HWC [0,1]
    arr = (arr - mean) / std                               # normalize
    arr = arr.transpose(2, 0, 1)[np.newaxis, ...]          # NCHW
    return arr.astype(np.float32)


def _infer_onnx(image: Image.Image, top_k: int = 3) -> tuple[list, str]:
    sess, input_name, classes, mean, std, image_size = _load_onnx()
    inp = _preprocess_for_onnx(image, image_size, mean, std)
    logits = sess.run(None, {input_name: inp})[0][0]       # (38,)
    # softmax
    exp = np.exp(logits - logits.max())
    probs = exp / exp.sum()
    order = np.argsort(probs)[::-1][:top_k]
    top = [(classes[i], float(probs[i])) for i in order]
    return top, "onnx_hf"


# ---------------------------------------------------------------------------
# Path 2: PyTorch CNN checkpoint
# ---------------------------------------------------------------------------

def _cnn_available() -> bool:
    if not CHECKPOINT_PATH.exists():
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


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


def _infer_cnn(image: Image.Image, top_k: int = 3) -> tuple[list, str]:
    model, classes, tf, torch = _load_cnn()
    with torch.no_grad():
        x = tf(image.convert("RGB")).unsqueeze(0)
        probs = torch.softmax(model(x), dim=1)[0]
    order = torch.argsort(probs, descending=True)[:top_k]
    top = [(classes[i], float(probs[i])) for i in order]
    return top, "cnn"


# ---------------------------------------------------------------------------
# Path 3: Demo heuristic fallback (sklearn RandomForest on color statistics)
# ---------------------------------------------------------------------------

def _load_demo():
    global _demo_cache
    if _demo_cache is not None:
        return _demo_cache
    with open(DEMO_MODEL_PATH, "rb") as f:
        payload = pickle.load(f)
    _demo_cache = payload
    return _demo_cache


def _infer_demo(image: Image.Image, top_k: int = 3) -> tuple[list, str]:
    from features import extract_features
    payload = _load_demo()
    clf = payload["model"]
    feats = extract_features(image).reshape(1, -1)
    probs = clf.predict_proba(feats)[0]
    order = probs.argsort()[::-1][:top_k]
    top = [(clf.classes_[i], float(probs[i])) for i in order]
    return top, "demo_heuristic"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _split_class_name(class_name: str) -> tuple[str, str]:
    """'Tomato___Early_blight' -> ('Tomato', 'Early blight')"""
    if "___" in class_name:
        crop, disease = class_name.split("___", 1)
    else:
        crop, disease = "Unknown", class_name
    # clean up underscores and extra parens from PlantVillage naming
    crop = crop.replace("_", " ").replace("(", "").replace(")", "").strip()
    disease = disease.replace("_", " ").strip()
    return crop, disease


def classify_image(image: Union[str, Path, Image.Image], top_k: int = 3) -> dict:
    """
    Classify a leaf image and return disease/crop prediction.

    Priority: ONNX (HuggingFace, 99.98% acc) > PyTorch CNN > Demo heuristic.
    """
    if isinstance(image, (str, Path)):
        image = Image.open(image)

    if _onnx_available():
        top, mode = _infer_onnx(image, top_k)
    elif _cnn_available():
        top, mode = _infer_cnn(image, top_k)
    else:
        top, mode = _infer_demo(image, top_k)

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

    if len(sys.argv) > 1:
        result = classify_image(sys.argv[1])
    else:
        # Synthesize a greenish leaf image for smoke testing
        rng = np.random.default_rng(0)
        arr = rng.integers(60, 180, size=(128, 128, 3)).astype("uint8")
        arr[:, :, 1] = np.clip(arr[:, :, 1] + 40, 0, 255)
        result = classify_image(Image.fromarray(arr))

    print(json.dumps(result, indent=2))
