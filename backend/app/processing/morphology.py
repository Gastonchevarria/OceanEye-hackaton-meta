"""
Morphological Target Extraction and Physical Parameter Estimation.

Performs connected-component analysis on the binary CFAR detection mask to
characterize detected naval targets:
- WGS84 Latitude and Longitude centroid conversion via Affine transform.
- Principal axes of inertia (eigenvalues of spatial moments matrix) to estimate:
  - Eslora (Estimated Length in meters)
  - Manga (Estimated Beam / Width in meters)
  - Heading / Orientation angle (degrees)
- Peak Radar Cross Section (RCS) in dB.
- Target Signal-to-Noise Ratio (SNR) in dB.
- Size filtering: eliminates sub-pixel clutter specks and large land masses.
"""

import numpy as np
from scipy.ndimage import label, center_of_mass
from typing import List, Optional, Tuple, Dict, Any
from pydantic import BaseModel, Field


class SarVesselDetection(BaseModel):
    id: str = Field(..., description="Unique target identifier (e.g. SAR-2026-001)")
    lat: float = Field(..., description="WGS84 Latitude of centroid")
    lon: float = Field(..., description="WGS84 Longitude of centroid")
    pixel_r: float = Field(..., description="Row coordinate in image")
    pixel_c: float = Field(..., description="Column coordinate in image")
    length_m: float = Field(..., description="Estimated vessel length (eslora) in meters")
    beam_m: float = Field(..., description="Estimated vessel beam (manga) in meters")
    heading_deg: float = Field(..., description="Estimated vessel heading in degrees (0-360)")
    peak_rcs_db: float = Field(..., description="Peak Radar Cross Section in dB")
    mean_rcs_db: float = Field(..., description="Mean Radar Cross Section in dB")
    snr_db: float = Field(..., description="Estimated target SNR over local clutter in dB")
    area_pixels: int = Field(..., description="Number of connected pixels")
    classification: str = Field(default="UNMATCHED_SAR", description="Tactical classification")


def pixel_to_wgs84(
    r: float,
    c: float,
    affine_transform: Optional[Tuple[float, float, float, float, float, float]] = None,
    bounds: Optional[Tuple[float, float, float, float]] = None,
    image_shape: Optional[Tuple[int, int]] = None
) -> Tuple[float, float]:
    """
    Convert image pixel coordinate (r, c) to WGS84 geographic coordinate (lat, lon).

    Can use either:
    1. Standard affine transform tuple: (c_origin, dx, rot_x, r_origin, rot_y, dy)
       where lon = c_origin + c * dx + r * rot_x
             lat = r_origin + c * rot_y + r * dy
    2. Bounding box tuple: (min_lon, min_lat, max_lon, max_lat) and image_shape (H, W).
    """
    if affine_transform is not None:
        c0, dx, rx, r0, ry, dy = affine_transform
        lon = c0 + c * dx + r * rx
        lat = r0 + c * ry + r * dy
        return float(lat), float(lon)

    if bounds is not None and image_shape is not None:
        min_lon, min_lat, max_lon, max_lat = bounds
        h, w = image_shape
        # r goes from 0 (top/max_lat) to h (bottom/min_lat)
        # c goes from 0 (left/min_lon) to w (right/max_lon)
        lat = max_lat - (r / max(h - 1, 1)) * (max_lat - min_lat)
        lon = min_lon + (c / max(w - 1, 1)) * (max_lon - min_lon)
        return float(lat), float(lon)

    # Fallback default centered in Mile 201 corridor
    return float(-45.0 - (r * 0.0001)), float(-60.0 + (c * 0.0001))


def estimate_inertial_dimensions(
    component_coords: np.ndarray,
    pixel_res_m: float = 10.0
) -> Tuple[float, float, float]:
    """
    Estimate length, beam, and heading using second-order central spatial moments.

    Args:
        component_coords: (N, 2) array of (row, col) pixel coordinates.
        pixel_res_m: Pixel resolution in meters (Sentinel-1 GRD High Res ~ 10m).

    Returns:
        (length_m, beam_m, heading_deg)
    """
    if len(component_coords) < 2:
        return 20.0, 10.0, 0.0

    r = component_coords[:, 0].astype(np.float64)
    c = component_coords[:, 1].astype(np.float64)

    # Centroid
    r_bar = np.mean(r)
    c_bar = np.mean(c)

    # Central moments
    mu_20 = np.mean((r - r_bar) ** 2)
    mu_02 = np.mean((c - c_bar) ** 2)
    mu_11 = np.mean((r - r_bar) * (c - c_bar))

    # Covariance matrix
    cov = np.array([[mu_20, mu_11], [mu_11, mu_02]])
    eigvals, eigvecs = np.linalg.eigh(cov)

    # Principal moments
    lambda_major = max(eigvals[1], 0.01)
    lambda_minor = max(eigvals[0], 0.01)

    # Semi-axes length: 4 * sqrt(lambda) matches uniform distribution standard deviation
    length_m = max(float(4.0 * np.sqrt(lambda_major) * pixel_res_m), 15.0)
    beam_m = max(float(4.0 * np.sqrt(lambda_minor) * pixel_res_m), 5.0)

    # Orientation (angle with respect to North)
    # Row increases South (negative Lat), Col increases East (positive Lon)
    major_vec = eigvecs[:, 1]
    angle_rad = np.arctan2(major_vec[1], -major_vec[0])
    heading_deg = float(np.degrees(angle_rad) % 360.0)

    return length_m, beam_m, heading_deg


def extract_sar_targets(
    detection_mask: np.ndarray,
    intensity_linear: np.ndarray,
    threshold_map: Optional[np.ndarray] = None,
    pixel_res_m: float = 10.0,
    min_pixels: int = 3,
    max_pixels: int = 4000,
    affine_transform: Optional[Tuple[float, float, float, float, float, float]] = None,
    bounds: Optional[Tuple[float, float, float, float]] = None
) -> List[SarVesselDetection]:
    """
    Extract discrete naval targets from the binary CFAR detection mask.

    Args:
        detection_mask: 2D boolean array from CFAR.
        intensity_linear: 2D float32 array of calibrated linear intensity.
        threshold_map: Optional 2D float32 array of CFAR threshold map for SNR calculation.
        pixel_res_m: Ground range / azimuth resolution in meters.
        min_pixels: Minimum pixel area to filter false alarm salt-and-pepper noise.
        max_pixels: Maximum pixel area to filter islands/coastlines.
        affine_transform: Optional affine geotransform tuple.
        bounds: Optional (min_lon, min_lat, max_lon, max_lat) bounds.

    Returns:
        List of SarVesselDetection objects sorted by peak RCS descending.
    """
    labeled_mask, num_features = label(detection_mask)
    if num_features == 0:
        return []

    h, w = detection_mask.shape
    detections: List[SarVesselDetection] = []

    # Linear to dB helper
    def to_db(val: float) -> float:
        return float(10.0 * np.log10(max(val, 1e-10)))

    target_idx = 1
    for feat_id in range(1, num_features + 1):
        coords = np.argwhere(labeled_mask == feat_id)
        area = len(coords)
        if area < min_pixels or area > max_pixels:
            continue

        r_coords = coords[:, 0]
        c_coords = coords[:, 1]
        r_c = float(np.mean(r_coords))
        c_c = float(np.mean(c_coords))

        lat, lon = pixel_to_wgs84(
            r_c, c_c,
            affine_transform=affine_transform,
            bounds=bounds,
            image_shape=(h, w)
        )

        length_m, beam_m, heading_deg = estimate_inertial_dimensions(coords, pixel_res_m)

        comp_intensities = intensity_linear[r_coords, c_coords]
        peak_lin = float(np.max(comp_intensities))
        mean_lin = float(np.mean(comp_intensities))

        peak_rcs_db = round(to_db(peak_lin), 1)
        mean_rcs_db = round(to_db(mean_lin), 1)

        if threshold_map is not None:
            comp_thresh = threshold_map[r_coords, c_coords]
            mean_thresh = float(np.mean(comp_thresh))
            snr_db = round(to_db(max(mean_lin / max(mean_thresh, 1e-10), 1e-3)), 1)
        else:
            snr_db = round(peak_rcs_db - 15.0, 1)

        det = SarVesselDetection(
            id=f"SAR-TGT-{target_idx:03d}",
            lat=round(lat, 5),
            lon=round(lon, 5),
            pixel_r=round(r_c, 1),
            pixel_c=round(c_c, 1),
            length_m=round(length_m, 1),
            beam_m=round(beam_m, 1),
            heading_deg=round(heading_deg, 1),
            peak_rcs_db=peak_rcs_db,
            mean_rcs_db=mean_rcs_db,
            snr_db=snr_db,
            area_pixels=area,
            classification="UNMATCHED_SAR"
        )
        detections.append(det)
        target_idx += 1

    # Sort descending by peak RCS (brightest targets first)
    detections.sort(key=lambda d: d.peak_rcs_db, reverse=True)
    return detections
