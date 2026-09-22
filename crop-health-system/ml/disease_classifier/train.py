"""
Train the disease classifier on a PlantVillage-style dataset.

Expected data layout (standard torchvision ImageFolder format):

    data/train/Tomato___Early_blight/*.jpg
    data/train/Tomato___Late_blight/*.jpg
    data/train/Tomato___healthy/*.jpg
    ...
    data/val/Tomato___Early_blight/*.jpg
    ...

Get the dataset:
    PlantVillage (38 classes, ~54k images) is mirrored in several places,
    e.g. search "PlantVillage dataset" on Kaggle. Download it, split into
    train/val (80/20 is a reasonable default), and arrange it as above.
    If you're also detecting local pests/diseases not in PlantVillage,
    add your own labeled folders alongside the PlantVillage ones and update
    labels.json to match.

Usage:
    python train.py --data-dir ./data --epochs 15 --arch efficientnet
    python train.py --data-dir ./data --epochs 5  --arch leafnet   # fast smoke test

Output:
    Saves the best checkpoint to ./checkpoints/disease_classifier.pt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from model import LeafNet, build_efficientnet, load_classes, input_size


def get_transforms():
    from torchvision import transforms

    size = input_size()
    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.8, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    val_tf = transforms.Compose([
        transforms.Resize(size),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ])
    return train_tf, val_tf


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=str, default="./data")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--arch", choices=["leafnet", "efficientnet"], default="efficientnet")
    parser.add_argument("--out", type=str, default="./checkpoints/disease_classifier.pt")
    args = parser.parse_args()

    from torchvision.datasets import ImageFolder

    train_tf, val_tf = get_transforms()
    train_dir = Path(args.data_dir) / "train"
    val_dir = Path(args.data_dir) / "val"
    if not train_dir.exists():
        raise SystemExit(
            f"No training data found at {train_dir}. See the module docstring "
            f"in train.py for the expected folder layout and where to get "
            f"the PlantVillage dataset."
        )

    train_ds = ImageFolder(train_dir, transform=train_tf)
    val_ds = ImageFolder(val_dir, transform=val_tf) if val_dir.exists() else None

    classes = load_classes()
    if train_ds.classes != classes:
        print("WARNING: dataset folder names don't match labels.json exactly. "
              "Update labels.json to match train_ds.classes for consistent "
              "label ordering:")
        print(train_ds.classes)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = (LeafNet(len(train_ds.classes)) if args.arch == "leafnet"
              else build_efficientnet(len(train_ds.classes), pretrained=True)).to(device)

    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True, num_workers=2)
    val_loader = (DataLoader(val_ds, batch_size=args.batch_size, num_workers=2)
                  if val_ds else None)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    criterion = nn.CrossEntropyLoss()

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    best_acc = 0.0

    for epoch in range(args.epochs):
        model.train()
        running_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * images.size(0)
        scheduler.step()
        train_loss = running_loss / len(train_ds)

        msg = f"epoch {epoch+1}/{args.epochs} | train_loss {train_loss:.4f}"

        if val_loader:
            model.eval()
            correct, total = 0, 0
            with torch.no_grad():
                for images, labels in val_loader:
                    images, labels = images.to(device), labels.to(device)
                    preds = model(images).argmax(dim=1)
                    correct += (preds == labels).sum().item()
                    total += labels.size(0)
            val_acc = correct / max(total, 1)
            msg += f" | val_acc {val_acc:.4f}"

            if val_acc > best_acc:
                best_acc = val_acc
                torch.save({
                    "model_state": model.state_dict(),
                    "classes": train_ds.classes,
                    "arch": args.arch,
                }, args.out)
                msg += "  (saved best)"

        print(msg)

    if not val_loader:
        torch.save({
            "model_state": model.state_dict(),
            "classes": train_ds.classes,
            "arch": args.arch,
        }, args.out)

    print(f"Done. Checkpoint at {args.out}")


if __name__ == "__main__":
    main()
