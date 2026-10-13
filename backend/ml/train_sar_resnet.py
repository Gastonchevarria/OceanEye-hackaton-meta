"""
Train OceanEyeSarNet on Real LS-SSDD Dual-Pol Sentinel-1 SAR Chips.
Evaluates on independent test split and exports to ONNX for Cloud Run deployment.
"""

import os
import json
import time
import math
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from ml.model import OceanEyeSarNet


class NpzSarDataset(Dataset):
    def __init__(self, npz_path: str):
        data = np.load(npz_path)
        self.chips = data["chips"]  # [N, 2, 64, 64]
        self.is_vessel = data["is_vessel"]  # [N]
        self.is_fishing = data["is_fishing"]  # [N]
        self.length_m = data["length_m"]  # [N]

    def __len__(self):
        return len(self.is_vessel)

    def __getitem__(self, idx):
        chip = torch.tensor(self.chips[idx], dtype=torch.float32)
        vessel = torch.tensor([self.is_vessel[idx]], dtype=torch.float32)
        fishing = torch.tensor([self.is_fishing[idx]], dtype=torch.float32)
        length = torch.tensor([self.length_m[idx]], dtype=torch.float32)
        return chip, vessel, fishing, length


def train_model(
    train_npz: str = "data/sar_chips/train_chips.npz",
    val_npz: str = "data/sar_chips/valid_chips.npz",
    test_npz: str = "data/sar_chips/test_chips.npz",
    epochs: int = 10,
    batch_size: int = 64,
    lr: float = 1e-3,
    onnx_out: str = "backend/ml/oceaneye_sar_resnet.onnx",
    metrics_out: str = "backend/ml/evaluation_metrics.json"
):
    # Device selection: MPS (Metal Performance Shaders on Mac) > CUDA > CPU
    if torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    print(f"🚀 Training OceanEyeSarNet on device: {device}")

    train_ds = NpzSarDataset(train_npz)
    val_ds = NpzSarDataset(val_npz)
    test_ds = NpzSarDataset(test_npz)

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)
    test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

    print(f"Dataset splits: {len(train_ds)} train, {len(val_ds)} val, {len(test_ds)} test.")

    model = OceanEyeSarNet().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    bce_vessel = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([1.2]).to(device))
    bce_fishing = nn.BCEWithLogitsLoss()
    l1_length = nn.SmoothL1Loss()

    best_val_f1 = 0.0

    t_start = time.perf_counter()

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0

        for chips, y_v, y_f, y_l in train_loader:
            chips = chips.to(device)
            y_v, y_f, y_l = y_v.to(device), y_f.to(device), y_l.to(device)

            optimizer.zero_grad()
            logit_v, logit_f, pred_l = model(chips)

            loss_v = bce_vessel(logit_v, y_v)
            loss_f = bce_fishing(logit_f, y_f)
            # Length loss only calculated for positive vessels
            mask_v = (y_v > 0.5)
            loss_l = l1_length(pred_l[mask_v], y_l[mask_v]) if mask_v.sum() > 0 else 0.0

            loss = loss_v + 0.5 * loss_f + 0.01 * loss_l
            loss.backward()
            optimizer.step()

            total_loss += loss.item()

        scheduler.step()

        # Validation
        model.eval()
        tp, fp, fn = 0, 0, 0
        with torch.no_grad():
            for chips, y_v, _, _ in val_loader:
                chips, y_v = chips.to(device), y_v.to(device)
                logit_v, _, _ = model(chips)
                preds = (torch.sigmoid(logit_v) > 0.5).float()
                tp += ((preds == 1) & (y_v == 1)).sum().item()
                fp += ((preds == 1) & (y_v == 0)).sum().item()
                fn += ((preds == 0) & (y_v == 1)).sum().item()

        prec = tp / max(tp + fp, 1)
        rec = tp / max(tp + fn, 1)
        f1 = 2 * (prec * rec) / max(prec + rec, 1e-4)

        print(f"Epoch {epoch:02d}/{epochs:02d} | Loss: {total_loss/len(train_loader):.4f} | Val Prec: {prec*100:.1f}% | Val Rec: {rec*100:.1f}% | Val F1: {f1:.4f}")

    total_training_sec = round(time.perf_counter() - t_start, 2)

    # Final Evaluation on Independent Test Split
    model.eval()
    t_test_start = time.perf_counter()
    tp_t, fp_t, fn_t, tn_t = 0, 0, 0, 0
    length_errors = []

    with torch.no_grad():
        for chips, y_v, y_f, y_l in test_loader:
            chips, y_v, y_l = chips.to(device), y_v.to(device), y_l.to(device)
            logit_v, logit_f, pred_l = model(chips)

            probs = torch.sigmoid(logit_v)
            preds = (probs > 0.5).float()

            tp_t += ((preds == 1) & (y_v == 1)).sum().item()
            fp_t += ((preds == 1) & (y_v == 0)).sum().item()
            fn_t += ((preds == 0) & (y_v == 1)).sum().item()
            tn_t += ((preds == 0) & (y_v == 0)).sum().item()

            mask_pos = (y_v == 1)
            if mask_pos.sum() > 0:
                err = torch.abs(pred_l[mask_pos] - y_l[mask_pos]).cpu().numpy()
                length_errors.extend(err.flatten().tolist())

    test_latency_ms = round(((time.perf_counter() - t_test_start) / len(test_ds)) * 1000.0, 3)

    test_precision = tp_t / max(tp_t + fp_t, 1)
    test_recall = tp_t / max(tp_t + fn_t, 1)
    test_f1 = 2 * (test_precision * test_recall) / max(test_precision + test_recall, 1e-4)
    test_accuracy = (tp_t + tn_t) / max(tp_t + tn_t + fp_t + fn_t, 1)
    mean_length_mae = float(np.mean(length_errors)) if length_errors else 0.0

    print("\n" + "="*50)
    print("📊 RESULTADOS OFICIALES EN TEST SPLIT INDEPENDIENTE:")
    print(f"- Total Muestras Test: {len(test_ds)}")
    print(f"- Precisión (Precision): {test_precision*100:.2f}%")
    print(f"- Exhaustividad (Recall): {test_recall*100:.2f}%")
    print(f"- F1-Score: {test_f1:.4f}")
    print(f"- Exactitud (Accuracy): {test_accuracy*100:.2f}%")
    print(f"- Error Medio de Eslora (MAE): {mean_length_mae:.2f} m")
    print(f"- Latencia por Chip: {test_latency_ms:.2f} ms")
    print("="*50 + "\n")

    # Export to ONNX (CPU Execution for Cloud Run)
    os.makedirs(os.path.dirname(onnx_out), exist_ok=True)
    model.eval()
    cpu_model = OceanEyeSarNet().to("cpu")
    cpu_model.load_state_dict({k: v.to("cpu") for k, v in model.state_dict().items()})

    dummy_input = torch.randn(1, 2, 64, 64, dtype=torch.float32)
    try:
        torch.onnx.export(
            cpu_model,
            dummy_input,
            onnx_out,
            input_names=["input"],
            output_names=["vessel_logit", "fishing_logit", "length_pred"],
            dynamic_axes={"input": {0: "batch_size"}},
            opset_version=14,
            dynamo=False
        )
        print(f"✅ Modelo ONNX exportado exitosamente en: {onnx_out}")
    except Exception as e:
        print(f"⚠️ ONNX export warning: {e}. Falling back to standard TorchScript.")
        traced = torch.jit.trace(cpu_model, dummy_input)
        traced.save(onnx_out.replace(".onnx", ".torchscript.pt"))

    # Save PyTorch weights
    pt_out = onnx_out.replace(".onnx", ".pt")
    torch.save(cpu_model.state_dict(), pt_out)
    print(f"✅ Pesos PyTorch guardados en: {pt_out}")

    metrics = {
        "dataset": "LS-SSDD Sentinel-1 C-Band Dual-Pol (VV+VH)",
        "train_samples": len(train_ds),
        "val_samples": len(val_ds),
        "test_samples": len(test_ds),
        "epochs": epochs,
        "training_time_seconds": total_training_sec,
        "test_metrics": {
            "precision": round(test_precision, 4),
            "recall": round(test_recall, 4),
            "f1_score": round(test_f1, 4),
            "accuracy": round(test_accuracy, 4),
            "length_mae_meters": round(mean_length_mae, 2),
            "inference_latency_ms": test_latency_ms
        },
        "hardware_evaluated": str(device),
        "onnx_model_path": onnx_out
    }

    with open(metrics_out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"✅ Métricas guardadas en: {metrics_out}")

    return metrics


if __name__ == "__main__":
    train_model(epochs=10, batch_size=64)
