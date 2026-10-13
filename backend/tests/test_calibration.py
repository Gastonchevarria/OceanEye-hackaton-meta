"""
Unit tests for SAR radiometric calibration and dual-pol fusion.
"""

import pytest
import numpy as np
from app.processing.calibration import (
    calibrate_dn_to_sigma0_linear,
    sigma0_linear_to_db,
    calibrate_dn_to_sigma0_db
)
from app.processing.dual_pol_fusion import (
    fuse_dual_polarization,
    evaluate_polarimetric_gain
)
from app.processing.lee_filter import enhanced_lee_filter


def test_radiometric_calibration_values():
    # DN array with known values
    dn = np.array([[100, 200], [300, 400]], dtype=np.uint16)
    sigma0_lin = calibrate_dn_to_sigma0_linear(dn, lut=10.0)

    # (100 / 10)^2 = 100.0, (200 / 10)^2 = 400.0, etc.
    expected_lin = np.array([[100.0, 400.0], [900.0, 1600.0]], dtype=np.float32)
    np.testing.assert_allclose(sigma0_lin, expected_lin, rtol=1e-5)

    # In dB: 10 * log10(100) = 20.0 dB
    sigma0_db = sigma0_linear_to_db(sigma0_lin)
    assert np.isclose(sigma0_db[0, 0], 20.0, atol=1e-3)
    assert np.isclose(sigma0_db[0, 1], 26.02, atol=1e-2)


def test_dual_polarization_fusion_gain():
    np.random.seed(42)
    shape = (100, 100)

    # Clutter: high in VV (mean 10.0), low in VH (mean 1.0)
    vv_clutter = np.random.exponential(scale=10.0, size=shape).astype(np.float32)
    vh_clutter = np.random.exponential(scale=1.0, size=shape).astype(np.float32)

    # Metallic ship target at (50:55, 50:55): strong in VH (depolarized)
    target_mask = np.zeros(shape, dtype=bool)
    target_mask[50:55, 50:55] = True

    vv_clutter[target_mask] += 30.0   # VV target
    vh_clutter[target_mask] += 50.0   # VH target (high dihedral return)

    fused = fuse_dual_polarization(vv_clutter, vh_clutter, alpha=0.75)
    metrics = evaluate_polarimetric_gain(vv_clutter, vh_clutter, fused, target_mask)

    # Fused SCR must exhibit significant positive gain over single-pol VV
    assert metrics["gain_over_vv_db"] > 3.0
    assert metrics["scr_fused_db"] > metrics["scr_vv_db"]


def test_lee_filter_noise_smoothing():
    np.random.seed(42)
    shape = (80, 80)
    # Homogeneous sea clutter with Rayleigh/exponential speckle
    speckle_image = np.random.exponential(scale=5.0, size=shape).astype(np.float32)

    # Insert bright point target
    speckle_image[40, 40] = 200.0

    filtered = enhanced_lee_filter(speckle_image, window_size=7, enl=4.4)

    # Variance in homogeneous region should decrease
    var_orig = float(np.var(speckle_image[:30, :30]))
    var_filt = float(np.var(filtered[:30, :30]))
    assert var_filt < var_orig

    # Point target edge should be strongly preserved
    assert filtered[40, 40] > 100.0
