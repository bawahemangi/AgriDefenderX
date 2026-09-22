"""
CNN architecture for crop disease/pest classification from leaf images.

Two options are provided:

1. `LeafNet` -- a compact CNN built from scratch. No internet access or
   pretrained-weight download is required to instantiate or train it, which
   matters if you're training on a machine/CI runner with no internet
   access to download torchvision's ImageNet weights.

2. `build_efficientnet(pretrained=True)` -- wraps torchvision's
   EfficientNetV2-S. In practice this transfer-learns much faster and
   reaches higher accuracy than LeafNet trained from scratch, so prefer it
   whenever you *do* have internet access on your training machine.

Recommended real-world path:
    - Prototype and smoke-test with LeafNet (fast, no downloads).
    - Train the real submission model with build_efficientnet(pretrained=True)
      fine-tuned on PlantVillage (+ any local crop/pest images you collect).
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn as nn

LABELS_PATH = Path(__file__).parent / "labels.json"


def load_classes() -> list[str]:
    with open(LABELS_PATH) as f:
        return json.load(f)["classes"]


class ConvBlock(nn.Module):
    def __init__(self, in_ch: int, out_ch: int, stride: int = 1):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, stride=stride, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
        self.pool = nn.MaxPool2d(2)

    def forward(self, x):
        return self.pool(self.net(x))


class LeafNet(nn.Module):
    """Small from-scratch CNN. ~1.8M params. Good enough to smoke-test the
    whole pipeline (train -> infer -> serve) before investing in a bigger
    transfer-learned model."""

    def __init__(self, num_classes: int, in_ch: int = 3):
        super().__init__()
        self.features = nn.Sequential(
            ConvBlock(in_ch, 32),   # 224 -> 112
            ConvBlock(32, 64),      # 112 -> 56
            ConvBlock(64, 128),     # 56 -> 28
            ConvBlock(128, 256),    # 28 -> 14
        )
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Dropout(0.3),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        return self.head(self.features(x))


def build_efficientnet(num_classes: int, pretrained: bool = True) -> nn.Module:
    """Wraps torchvision EfficientNetV2-S with a replaced classifier head.

    NOTE: pretrained=True downloads ImageNet weights from
    download.pytorch.org the first time it's called -- do this on your
    training machine with normal internet access, not in a locked-down
    sandbox. Set pretrained=False to build the architecture with random
    initialization (no download), e.g. for CI smoke tests.
    """
    from torchvision import models

    weights = models.EfficientNet_V2_S_Weights.DEFAULT if pretrained else None
    net = models.efficientnet_v2_s(weights=weights)
    in_features = net.classifier[1].in_features
    net.classifier[1] = nn.Linear(in_features, num_classes)
    return net


def input_size() -> tuple[int, int]:
    return (224, 224)


if __name__ == "__main__":
    # Smoke test: verify the architecture is well-formed and a forward pass
    # produces the expected output shape. Doesn't need a dataset or GPU.
    classes = load_classes()
    model = LeafNet(num_classes=len(classes))
    dummy = torch.randn(2, 3, *input_size())
    out = model(dummy)
    assert out.shape == (2, len(classes)), out.shape
    print(f"OK -- LeafNet forward pass produced shape {tuple(out.shape)} "
          f"for {len(classes)} classes.")
