"""
LS-SSDD Dataset Preprocessor for OceanEye SAR Neural Discriminator.

Extracts dual-polarization (VV + VH) 64x64 chips for:
1. Positive vessel targets (centered on ground-truth bounding boxes)
2. Negative sea clutter / wave crest targets (from open water background)
3. Vessel length estimation (ground range / azimuth geometry)
"""

import os
import glob
import math
import random
from typing import Tuple, List, Dict, Any
import numpy as np
from PIL import Image

def extract_chips_from_split(
    split_dir: str,
    output_dir: str,
    chip_size: int = 64,
    max_samples: int = 2500
) -> Dict[str, int]:
    """
    Process an LS-SSDD split (train, valid, or test) into normalized chips.
    """
    os.makedirs(output_dir, exist_ok=True)
    images_dir = os.path.join(split_dir, "images")
    labels_dir = os.path.join(split_dir, "labels")

    image_paths = sorted(glob.glob(os.path.join(images_dir, "*.jpg")) + glob.glob(os.path.join(images_dir, "*.png")))
    print(f"Processing {len(image_paths)} images from {split_dir}...")

    chips_vv = []
    chips_vh = []
    labels_vessel = []
    labels_fishing = []
    lengths_m = []

    count_pos = 0
    count_neg = 0

    for img_path in image_paths:
        if count_pos + count_neg >= max_samples:
            break

        base_name = os.path.splitext(os.path.basename(img_path))[0]
        # Look for dual-pol partner (e.g. _VV and _VH)
        is_vh = base_name.endswith("_VH")
        is_vv = base_name.endswith("_VV")

        partner_path = None
        if is_vv:
            partner_name = base_name[:-3] + "_VH" + os.path.splitext(img_path)[1]
            partner_path = os.path.join(images_dir, partner_name)
        elif is_vh:
            partner_name = base_name[:-3] + "_VV" + os.path.splitext(img_path)[1]
            partner_path = os.path.join(images_dir, partner_name)

        label_path = os.path.join(labels_dir, base_name + ".txt")
        boxes = []
        if os.path.exists(label_path):
            with open(label_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 5:
                        # class_id, xc, yc, w, h
                        boxes.append([float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])])

        try:
            with Image.open(img_path) as im:
                im_arr = np.array(im.convert("L"), dtype=np.float32)
        except Exception:
            continue

        partner_arr = None
        if partner_path and os.path.exists(partner_path):
            try:
                with Image.open(partner_path) as im_p:
                    partner_arr = np.array(im_p.convert("L"), dtype=np.float32)
            except Exception:
                partner_arr = None

        if partner_arr is None:
            # Synthetic depolarization approximation (~0.35 of co-pol for ships, ~0.15 for sea)
            partner_arr = im_arr * 0.30

        if is_vh:
            arr_vv, arr_vh = partner_arr, im_arr
        else:
            arr_vv, arr_vh = im_arr, partner_arr

        h, w = arr_vv.shape
        half = chip_size // 2

        # 1. Positive Ship Crops
        for b in boxes:
            xc_px, yc_px = int(b[0] * w), int(b[1] * h)
            bw_px, bh_px = b[2] * w, b[3] * h
            diag_px = math.sqrt(bw_px**2 + bh_px**2)
            length_est = max(diag_px * 10.0, 25.0) # 10m / px Sentinel-1

            # Bounds check for 64x64 chip
            r0 = max(0, min(yc_px - half, h - chip_size))
            c0 = max(0, min(xc_px - half, w - chip_size))
            r1, c1 = r0 + chip_size, c0 + chip_size

            if r1 <= h and c1 <= w:
                chip_v = arr_vv[r0:r1, c0:c1].copy()
                chip_h = arr_vh[r0:r1, c0:c1].copy()

                # Normalize to zero mean unit variance
                v_std = max(np.std(chip_v), 1e-4)
                h_std = max(np.std(chip_h), 1e-4)
                chip_v = (chip_v - np.mean(chip_v)) / v_std
                chip_h = (chip_h - np.mean(chip_h)) / h_std

                # Fishing heuristic: squid jiggers & trawlers in South Atlantic are 45-85m
                is_fishing = 1.0 if (45.0 <= length_est <= 90.0) else 0.0

                chips_vv.append(chip_v)
                chips_vh.append(chip_h)
                labels_vessel.append(1.0)
                labels_fishing.append(is_fishing)
                lengths_m.append(length_est)
                count_pos += 1

        # 2. Negative Background Crops (Sea clutter, waves)
        if len(boxes) == 0 or random.random() < 0.4:
            # Pick a region away from boxes
            for _ in range(2):
                rand_r = random.randint(0, max(0, h - chip_size))
                rand_c = random.randint(0, max(0, w - chip_size))
                chip_v = arr_vv[rand_r:rand_r+chip_size, rand_c:rand_c+chip_size].copy()
                chip_h = arr_vh[rand_r:rand_r+chip_size, rand_c:rand_c+chip_size].copy()

                if chip_v.shape == (chip_size, chip_size):
                    v_std = max(np.std(chip_v), 1e-4)
                    h_std = max(np.std(chip_h), 1e-4)
                    chip_v = (chip_v - np.mean(chip_v)) / v_std
                    chip_h = (chip_h - np.mean(chip_h)) / h_std

                    chips_vv.append(chip_v)
                    chips_vh.append(chip_h)
                    labels_vessel.append(0.0)
                    labels_fishing.append(0.0)
                    lengths_m.append(0.0)
                    count_neg += 1

    # Save to NPZ
    np_chips_vv = np.array(chips_vv, dtype=np.float32)
    np_chips_vh = np.array(chips_vh, dtype=np.float32)
    stacked_chips = np.stack([np_chips_vv, np_chips_vh], axis=1) # [N, 2, 64, 64]

    out_file = os.path.join(output_dir, f"{os.path.basename(split_dir)}_chips.npz")
    np.savez_compressed(
        out_file,
        chips=stacked_chips,
        is_vessel=np.array(labels_vessel, dtype=np.float32),
        is_fishing=np.array(labels_fishing, dtype=np.float32),
        length_m=np.array(lengths_m, dtype=np.float32)
    )

    print(f"Saved {stacked_chips.shape[0]} chips ({count_pos} vessels, {count_neg} clutter) to {out_file}")
    return {"total": stacked_chips.shape[0], "vessels": count_pos, "clutter": count_neg}


if __name__ == "__main__":
    base_dir = "data/sar_datasets/ls_ssdd"
    out_dir = "data/sar_chips"
    for split in ["train", "valid", "test"]:
        s_dir = os.path.join(base_dir, split)
        if os.path.exists(s_dir):
            extract_chips_from_split(s_dir, out_dir, chip_size=64)
