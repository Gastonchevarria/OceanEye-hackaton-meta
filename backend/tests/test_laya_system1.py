"""
Unit tests for LAYA: Ultra-Low Latency Deterministic Reflex Engine (Sistema 1).
"""

import time
import pytest
import numpy as np
from datetime import datetime, timezone

from app.laya.fast_path_triage import fast_path_triage_scene
from app.laya.ais_guardian import evaluate_ais_telemetry
from app.laya.custody_gateway import (
    seal_forensic_evidence_laya,
    verify_forensic_signature
)
from app.processing.morphology import SarVesselDetection


def test_laya_fast_path_triage_latency_and_rejection():
    # 600x600 scene with 15 ship returns and mostly open water
    np.random.seed(42)
    shape = (600, 600)
    sea = np.random.exponential(scale=5.0, size=shape).astype(np.float32)

    # Insert 3 ships in specific tiles
    sea[100:104, 100:104] += 300.0
    sea[250:254, 400:404] += 300.0

    report, anomalies = fast_path_triage_scene(sea, tile_size=120)

    # Must execute in < 40 ms (Sistema 1 requirement)
    assert report.triage_latency_ms < 40.0, f"Triage took {report.triage_latency_ms}ms, exceeded 40ms"

    # Rejection rate should be high (> 75-80%)
    assert report.rejection_rate_percent >= 75.0, f"Rejection rate was {report.rejection_rate_percent}%"

    # Active slices must include the ship tiles
    assert report.active_tiles >= 2
    assert report.discarded_tiles >= 15


def test_laya_ais_guardian_rules():
    t_now = datetime(2026, 4, 15, 14, 0, 0, tzinfo=timezone.utc)

    # 1. Test Rule 1: Proximity to EEZ (< 5 NM)
    # At Lat -45.0, Lon -55.80 is the boundary. Lat -45.0, Lon -55.75 is ~2.1 NM outside.
    report_prox = {
        "mmsi": "413000111",
        "name": "NEAR BORDER JIGGER",
        "lat": -45.0,
        "lon": -55.75,
        "sog": 2.0,
        "cog": 270.0,
        "last_seen": t_now.isoformat()
    }
    verdict_1 = evaluate_ais_telemetry(report_prox, now_utc=t_now)
    assert verdict_1.is_anomaly is True
    assert any(a.rule_name == "ZEE_BUFFER_PROXIMITY_ALERT" for a in verdict_1.alerts)
    assert verdict_1.evaluation_latency_ms < 40.0

    # 2. Test Rule 2: Coordinate Teleportation (Spoofing)
    prev_report = {
        "mmsi": "413999888",
        "name": "TELEPORT JIGGER",
        "lat": -45.0,
        "lon": -60.0,
        "last_seen": t_now.isoformat()
    }
    # 5 minutes later, jumped 40 NM East
    curr_report = {
        "mmsi": "413999888",
        "name": "TELEPORT JIGGER",
        "lat": -45.0,
        "lon": -59.05,
        "last_seen": datetime(2026, 4, 15, 14, 5, 0, tzinfo=timezone.utc).isoformat()
    }
    verdict_2 = evaluate_ais_telemetry(curr_report, previous_report=prev_report, now_utc=t_now)
    assert any(a.rule_name == "AIS_SPOOFING_COORDINATE_TELEPORTATION" for a in verdict_2.alerts)

    # 3. Test Rule 3: Dead-Drop Blackout Trigger in Blue Hole corridor
    blackout_report = {
        "mmsi": "413222333",
        "name": "BLACKOUT SQUID 09",
        "lat": -45.50,
        "lon": -59.80,
        "ais_disabled": True,
        "last_seen": t_now.isoformat()
    }
    verdict_3 = evaluate_ais_telemetry(blackout_report, now_utc=t_now)
    assert any(a.rule_name == "DEAD_DROP_BLACKOUT_TRIGGER" for a in verdict_3.alerts)
    assert verdict_3.satellite_tasking_order is not None
    assert "TASK_SENTINEL1_INTERCEPT_ORDER" in verdict_3.alerts[-1].action_taken


def test_laya_ed25519_custody_sealing_and_verification():
    dark_vessel = SarVesselDetection(
        id="SAR-TGT-007",
        lat=-45.85, lon=-60.25,
        pixel_r=320, pixel_c=280,
        length_m=72.0, beam_m=13.0, heading_deg=180.0,
        peak_rcs_db=52.4, mean_rcs_db=38.0, snr_db=22.0,
        area_pixels=15,
        classification="DARK_VESSEL"
    )

    cert = seal_forensic_evidence_laya(dark_vessel, scene_id="S1A_IW_GRDH_TEST")

    # Latency sub-30ms
    assert cert.sealing_latency_ms < 30.0
    assert cert.evidentiary_status == "CRYPTOGRAPHICALLY_SEALED_VALID"
    assert len(cert.sha256_evidence_hash) == 64
    assert len(cert.ed25519_signature_base64) > 20

    # Verification: rebuild payload and verify signature with public key
    canonical_payload = {
        "dossier_id": cert.dossier_id,
        "target_id": cert.target_id,
        "scene_id": cert.scene_id,
        "satellite_sensor": "Sentinel-1A SAR C-Band",
        "timestamp_utc": cert.timestamp_utc,
        "lat": cert.wgs84_latitude,
        "lon": cert.wgs84_longitude,
        "distance_to_eez_nm": cert.distance_to_eez_nm,
        "boundary_status": cert.boundary_status,
        "length_meters": cert.length_meters,
        "beam_meters": cert.beam_meters,
        "peak_rcs_db": cert.peak_rcs_db,
        "legal_infraction": cert.legal_infraction,
        "legal_framework": [
            "Ley Federal de Pesca 24.922 (Art. 51)",
            "CONVEMAR Art. 56 y 73",
            "Resolucion OMI A.1106(29)"
        ],
        "radar_chip_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }

    # Should be valid
    is_valid = verify_forensic_signature(
        canonical_payload,
        cert.ed25519_signature_base64,
        cert.laya_public_key_hex
    )
    assert is_valid is True

    # Tamper test: modify coordinate by 0.001 degree -> signature MUST fail!
    tampered_payload = canonical_payload.copy()
    tampered_payload["lat"] = -45.851
    assert verify_forensic_signature(
        tampered_payload,
        cert.ed25519_signature_base64,
        cert.laya_public_key_hex
    ) is False


def test_laya_full_certificate_verification_and_tamper():
    from app.laya.custody_gateway import verify_laya_certificate

    dark_vessel = SarVesselDetection(
        id="SAR-TGT-008",
        lat=-45.72, lon=-60.10,
        pixel_r=250, pixel_c=310,
        length_m=68.0, beam_m=11.5, heading_deg=90.0,
        peak_rcs_db=49.0, mean_rcs_db=34.0, snr_db=19.0,
        area_pixels=12,
        classification="DARK_VESSEL"
    )

    cert = seal_forensic_evidence_laya(dark_vessel, scene_id="S1A_IW_GRDH_TEST2")
    cert_dict = cert.model_dump()

    # 1. Verification of pristine certificate
    verdict = verify_laya_certificate(cert_dict)
    assert verdict["is_valid"] is True
    assert verdict["status"] == "VALID_AUTHENTIC"
    assert verdict["signature_verified"] is True
    assert verdict["verification_latency_ms"] < 25.0

    # 2. Tampering test: change length_meters
    tampered_cert = cert_dict.copy()
    tampered_cert["length_meters"] = 999.0
    tampered_verdict = verify_laya_certificate(tampered_cert)
    assert tampered_verdict["is_valid"] is False
    assert tampered_verdict["status"] == "TAMPERED_OR_INVALID"

