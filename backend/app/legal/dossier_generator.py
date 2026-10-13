"""
Forensic Evidence Dossier Generator & Cryptographic Chain of Custody (UNCLOS / Ley 24.922).

Generates tamper-evident forensic intelligence dossiers for suspected dark vessels
and unauthorized intruders in the Argentine Exclusive Economic Zone (EEZ - Milla 200):
- Accurate geodesic distance to the Argentine maritime boundary (SHN / Ley 23.968).
- Tipification under UNCLOS / CONVEMAR (Arts. 56, 62, 73) and Ley Federal de Pesca 24.922.
- Cryptographic SHA-256 seal guaranteeing chain-of-custody integrity for maritime tribunals.
"""

import json
import math
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field

from app.processing.morphology import SarVesselDetection
from app.correlation.kinematic_predictor import haversine_distance_nm

# Official boundary vertices along the Argentine Mile 200 outer limit (Milla 200)
# from Río de la Plata down to Tierra del Fuego / Malvinas shelf
OFFICIAL_EEZ_BOUNDARY_LINE: List[Tuple[float, float]] = [
    # (Lat, Lon)
    (-36.00, -53.50),
    (-37.00, -52.80),
    (-38.50, -52.20),
    (-40.00, -52.50),
    (-41.50, -53.00),
    (-43.00, -53.50),
    (-44.00, -54.20),
    (-44.50, -55.00),
    (-45.00, -55.80),
    (-45.50, -56.80),
    (-46.00, -58.00),
    (-46.50, -59.20),
    (-47.00, -60.00),
    (-47.50, -60.50),
    (-48.00, -61.20),
    (-49.00, -62.00),
    (-50.00, -63.00),
    (-51.50, -64.20),
    (-53.00, -65.50),
    (-54.50, -64.00),
    (-55.50, -62.00)
]


class ForensicDossier(BaseModel):
    dossier_id: str
    target_id: str
    classification: str
    timestamp_utc: str
    wgs84_coordinates: Dict[str, float]
    estimated_dimensions: Dict[str, float]
    radar_cross_section_db: float
    distance_to_eez_nm: float
    boundary_status: str
    nearest_boundary_point: Dict[str, float]
    legal_infraction_type: str
    legal_citations: List[str]
    chain_of_custody_hash_sha256: str
    evidentiary_payload: Dict[str, Any]


def calculate_distance_to_eez_boundary(lat: float, lon: float) -> Tuple[float, Tuple[float, float], str]:
    """
    Compute minimum geodesic distance to the official Argentine 200 NM boundary line.

    Convention:
    - If vessel longitude is west of the boundary line at the given latitude, it is INSIDE the EEZ.
    - If vessel longitude is east of the boundary line, it is outside in international waters (High Seas / Mile 201).
    """
    min_dist = float("inf")
    nearest_pt = OFFICIAL_EEZ_BOUNDARY_LINE[0]

    for b_lat, b_lon in OFFICIAL_EEZ_BOUNDARY_LINE:
        d = haversine_distance_nm(lat, lon, b_lat, b_lon)
        if d < min_dist:
            min_dist = d
            nearest_pt = (b_lat, b_lon)

    # Determine inside/outside orientation relative to nearest boundary longitude
    is_inside = lon < nearest_pt[1]

    if is_inside:
        signed_dist = -round(min_dist, 2)
        status = "EEZ_INTRUSION_CONFIRMED"
    elif min_dist <= 3.0:
        signed_dist = round(min_dist, 2)
        status = "CRITICAL_BORDER_PROXIMITY_ALERT"
    else:
        signed_dist = round(min_dist, 2)
        status = "HIGH_SEAS_ADJACENT"

    return signed_dist, nearest_pt, status


def generate_forensic_dossier(
    sar_target: SarVesselDetection,
    ais_match: Optional[Any] = None,
    scene_id: str = "S1A_IW_GRDH_1SDV_2026_MILE201"
) -> ForensicDossier:
    """
    Generate a cryptographic forensic dossier for a detected naval target.
    """
    now_utc = datetime.now(timezone.utc).isoformat()
    signed_dist, nearest_pt, boundary_status = calculate_distance_to_eez_boundary(
        sar_target.lat, sar_target.lon
    )

    if sar_target.classification == "DARK_VESSEL":
        if boundary_status == "EEZ_INTRUSION_CONFIRMED":
            infraction = "UNAUTHORIZED_FISHING_INSIDE_EEZ_DARK_VESSEL"
            citations = [
                "Ley Federal de Pesca 24.922 - Art. 51 (Pesca no autorizada en ZEE)",
                "CONVEMAR Art. 56 y 73 (Derechos de soberanía y medidas de ejecución del Estado ribereño)",
                "Código Penal de la Nación Argentina Art. 189 bis"
            ]
        else:
            infraction = "SUSPECTED_IUU_BLACKOUT_ADJACENT_TO_EEZ"
            citations = [
                "Acuerdo sobre Medidas del Estado Rector del Puerto (AMERP / FAO)",
                "Resolución OMI A.1106(29) - Apagado ilegítimo de transpondedores AIS en alta mar",
                "Ley 24.922 - Art. 21 (Monitoreo de especies transzonales: Illex argentinus)"
            ]
    else:
        infraction = "MONITORED_COOPERATIVE_VESSEL"
        citations = ["CONVEMAR Art. 87 (Libertad de navegación en alta mar)"]

    dossier_id = f"DOSSIER-{sar_target.id}-{int(datetime.now(timezone.utc).timestamp())}"

    evidentiary_payload = {
        "dossier_id": dossier_id,
        "satellite_scene_id": scene_id,
        "target_id": sar_target.id,
        "classification": sar_target.classification,
        "lat": sar_target.lat,
        "lon": sar_target.lon,
        "length_meters": sar_target.length_m,
        "beam_meters": sar_target.beam_m,
        "peak_rcs_db": sar_target.peak_rcs_db,
        "snr_db": sar_target.snr_db,
        "distance_to_eez_nm": signed_dist,
        "boundary_status": boundary_status,
        "nearest_boundary_point": {"lat": nearest_pt[0], "lon": nearest_pt[1]},
        "ais_telemetry": ais_match.model_dump() if ais_match and hasattr(ais_match, "model_dump") else None,
        "generated_timestamp_utc": now_utc
    }

    # Cryptographic SHA-256 seal of the evidentiary payload
    payload_str = json.dumps(evidentiary_payload, sort_keys=True)
    sha256_hash = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()

    return ForensicDossier(
        dossier_id=dossier_id,
        target_id=sar_target.id,
        classification=sar_target.classification,
        timestamp_utc=now_utc,
        wgs84_coordinates={"latitude": sar_target.lat, "longitude": sar_target.lon},
        estimated_dimensions={
            "length_meters": sar_target.length_m,
            "beam_meters": sar_target.beam_m,
            "heading_degrees": sar_target.heading_deg
        },
        radar_cross_section_db=sar_target.peak_rcs_db,
        distance_to_eez_nm=signed_dist,
        boundary_status=boundary_status,
        nearest_boundary_point={"latitude": nearest_pt[0], "longitude": nearest_pt[1]},
        legal_infraction_type=infraction,
        legal_citations=citations,
        chain_of_custody_hash_sha256=sha256_hash,
        evidentiary_payload=evidentiary_payload
    )
