"""
Benchmark and validation tests for 2D CA-CFAR O(1) and Anti-Masking.
"""

import time
import pytest
import numpy as np
from app.processing.cfar_detector import ca_cfar_2d
from app.processing.morphology import extract_sar_targets


def test_cfar_execution_speed_benchmark():
    """
    Ensure the O(1) boxcar CFAR processes a 1000x1000 sub-scene in < 1.0 second on CPU.
    """
    np.random.seed(42)
    shape = (1000, 1000)
    image = np.random.exponential(scale=10.0, size=shape).astype(np.float32)

    # Insert 10 targets
    for i in range(10):
        r, c = (i + 1) * 90, (i + 1) * 90
        image[r:r+3, c:c+3] = 400.0

    start_time = time.perf_counter()
    mask, thresh = ca_cfar_2d(image, guard_size=5, train_size=21, pfa=1e-5, anti_masking=True)
    duration = time.perf_counter() - start_time

    assert duration < 1.0, f"CFAR execution took {duration:.3f}s, exceeding 1.0s limit"
    assert np.any(mask)
    assert thresh.shape == shape


def test_cfar_anti_masking_dense_fleet():
    """
    Test that two vessels in close proximity (simulating Chinese squid jiggers in Mile 201)
    are BOTH detected without mutual masking when anti-masking is enabled.
    """
    np.random.seed(42)
    shape = (200, 200)
    # Background sea clutter
    image = np.random.exponential(scale=5.0, size=shape).astype(np.float32)

    # Place two vessels separated by only 8 pixels (inside each other's 21x21 training window)
    vessel_1 = (100, 100)
    vessel_2 = (100, 108)

    image[vessel_1[0]-1:vessel_1[0]+2, vessel_1[1]-1:vessel_1[1]+2] = 250.0
    image[vessel_2[0]-1:vessel_2[0]+2, vessel_2[1]-1:vessel_2[1]+2] = 250.0

    # With anti_masking=True, both ships must be detected
    mask, _ = ca_cfar_2d(image, guard_size=5, train_size=21, pfa=1e-5, anti_masking=True)

    # Verify both vessel centers are flagged as detected
    assert mask[vessel_1[0], vessel_1[1]] is True or mask[vessel_1[0], vessel_1[1]] == 1
    assert mask[vessel_2[0], vessel_2[1]] is True or mask[vessel_2[0], vessel_2[1]] == 1

    targets = extract_sar_targets(mask, image, pixel_res_m=10.0, min_pixels=2)
    assert len(targets) >= 2, f"Expected at least 2 distinct targets, found {len(targets)}"
