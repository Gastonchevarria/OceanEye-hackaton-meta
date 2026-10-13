"""
Unit tests for Kinematic Correlator and Hungarian Matching Engine.
"""

from datetime import datetime, timezone, timedelta
import pytest
from app.processing.morphology import SarVesselDetection
from app.correlation.kinematic_predictor import (
    project_ais_position,
    project_vessels_to_sar_time,
    haversine_distance_nm
)
from app.correlation.hungarian_matcher import match_sar_with_ais


def test_dead_reckoning_projection():
    # Vessel at lat -45.0, lon -60.0 heading North (0 deg) at 12 knots
    lat, lon = -45.0, -60.0
    sog, cog = 12.0, 0.0
    delta_seconds = 3600.0  # 1 hour

    # In 1 hour at 12 knots, vessel travels 12 NM = 0.2 degrees North
    proj_lat, proj_lon, unc_nm = project_ais_position(lat, lon, sog, cog, delta_seconds)

    assert pytest.approx(proj_lat, abs=0.01) == -44.8
    assert pytest.approx(proj_lon, abs=0.01) == -60.0
    assert unc_nm > 0.5


def test_hungarian_matching_with_dark_and_ghost_vessels():
    t_sar = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc)

    # 1. SAR Target 1: will match with AIS vessel 1
    sar_1 = SarVesselDetection(
        id="SAR-001",
        lat=-45.10, lon=-60.20,
        pixel_r=100, pixel_c=100,
        length_m=65.0, beam_m=12.0, heading_deg=180.0,
        peak_rcs_db=32.0, mean_rcs_db=25.0, snr_db=18.0,
        area_pixels=12
    )

    # 2. SAR Target 2: has NO matching AIS -> MUST BE DARK VESSEL
    sar_2_dark = SarVesselDetection(
        id="SAR-002",
        lat=-45.85, lon=-60.75,
        pixel_r=300, pixel_c=300,
        length_m=72.0, beam_m=14.0, heading_deg=45.0,
        peak_rcs_db=38.0, mean_rcs_db=28.0, snr_db=21.0,
        area_pixels=16
    )

    # AIS Vessel 1: close to SAR-001
    ais_raw = [
        {
            "mmsi": "413294810",
            "name": "LU RONG YU 588",
            "flag": "China",
            "vessel_type": "Squid Jigger",
            "lat": -45.09,
            "lon": -60.20,
            "heading": 180.0,
            "avg_speed": 1.0,
            "last_seen": t_sar.isoformat()
        },
        # AIS Vessel 2: inside SAR scene (-45.30, -60.50), but NO physical SAR target there -> MUST BE GHOST AIS
        {
            "mmsi": "999888777",
            "name": "GHOST JIGGER 01",
            "flag": "Unknown",
            "vessel_type": "Trawler",
            "lat": -45.30,
            "lon": -60.50,
            "heading": 90.0,
            "avg_speed": 0.0,
            "last_seen": t_sar.isoformat()
        }
    ]

    proj_ais = project_vessels_to_sar_time(ais_raw, t_sar)
    bbox = (-61.0, -46.0, -60.0, -45.0)  # [min_lon, min_lat, max_lon, max_lat]

    result = match_sar_with_ais(
        sar_targets=[sar_1, sar_2_dark],
        ais_vessels=proj_ais,
        sar_bbox=bbox,
        gating_distance_nm=3.0
    )

    # Verify counts
    assert result.total_sar_targets == 2
    assert result.total_confirmed == 1
    assert result.total_dark_vessels == 1
    assert result.total_ghost_ais == 1

    # Verify identities
    assert result.confirmed_matches[0].sar_target.id == "SAR-001"
    assert result.confirmed_matches[0].ais_vessel.mmsi == "413294810"

    assert result.dark_vessels[0].id == "SAR-002"
    assert result.ghost_ais_vessels[0].mmsi == "999888777"
