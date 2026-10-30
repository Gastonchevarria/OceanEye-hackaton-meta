"""
Regression and unit tests for Neuro-Symbolic Validator fixes F1-F6
(see specs/arena_replay/README.md).
"""

import json
import os

from app.legal.rules_engine import evaluate_maritime_case
from app.legal.legal_eval_harness import SCENARIOS_30
from app.legal.neuro_symbolic_validator import (
    EvidenceVector,
    validate_legal_narrative,
    validate_with_spans,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ARTIFACT_PATH = os.path.join(REPO_ROOT, "backend/ml/meta_muse_sam31_benchmark_2026.json")


def _slice_u16(s: str, start: int, end: int) -> str:
    b = s.encode("utf-16-le")
    return b[start * 2 : end * 2].decode("utf-16-le")


def _make_ev(sc: dict, use_flags: bool = True) -> EvidenceVector:
    lic = sc.get("has_valid_license", False) if use_flags else False
    nat = sc.get("is_national_flag", False) if use_flags else False
    v = evaluate_maritime_case(
        sc["distance_to_eez_nm"],
        sc["classification"],
        has_valid_license=lic,
        is_national_flag=nat,
    )
    return EvidenceVector(
        target_id=sc["case_id"],
        lat=sc["lat"],
        lon=sc["lon"],
        length_m=sc["length_m"],
        beam_m=sc["beam_m"],
        peak_rcs_db=sc["peak_rcs_db"],
        snr_db=sc["snr_db"],
        distance_to_eez_nm=sc["distance_to_eez_nm"],
        classification=sc["classification"],
        boundary_status="INSIDE_ARGENTINE_EEZ" if sc["distance_to_eez_nm"] < 0 else "OUTSIDE_EEZ_BUFFER",
        legal_verdict=v,
    )


def test_all_16_artifact_false_positives_are_zero_in_fixed_mode():
    """All 16 legacy false positives on the 60 comparative previews must produce 0 findings."""
    with open(ARTIFACT_PATH, "r", encoding="utf-8") as fh:
        art = json.load(fh)
    scen_by_id = {s["case_id"]: s for s in SCENARIOS_30}
    cmp_ = art["comparative_30_case_evaluation"]

    legacy_fp_total = 0
    for key in ("muse_wonder_results", "muse_spark_results"):
        for r in cmp_[key]:
            sc = scen_by_id[r["case_id"]]
            ev = _make_ev(sc, use_flags=False)
            _, fixed_findings = validate_with_spans(r["narrative_preview"], ev, legacy_parity=False)
            assert fixed_findings == [], f"Unexpected finding in {r['case_id']}: {fixed_findings}"
            _, leg_findings = validate_with_spans(r["narrative_preview"], ev, legacy_parity=True)
            legacy_fp_total += len(leg_findings)

    assert legacy_fp_total == 16


def test_f1_hemisphere_tokens_and_id_boundaries():
    sc = SCENARIOS_30[0]  # TC-EEZ-001: lat=-45.2, lon=-59.8
    ev = _make_ev(sc)

    # Identifiers and Spanish words must not trigger coordinate claims
    clean = "Caso TC-EEZ-001 en Milla 200 en escena S1A_IW_GRDH_1SDV_2026 con rumbo -57.1 se dirige al sur."
    _, findings = validate_with_spans(clean, ev)
    assert findings == []

    # Real wrong coordinates with hemisphere tokens must still trigger
    wrong = "Buque detectado en 25.50N y 40.20W (o 30.0°S, 50.0 S)."
    txt, findings = validate_with_spans(wrong, ev)
    rules = [f["rule_id"] for f in findings]
    assert rules.count("NUM-LAT-001") == 3
    assert rules.count("NUM-LON-001") == 1
    for f in findings:
        assert _slice_u16(txt, f["char_start"], f["char_end"]) == f["matched_text"]


def test_f2_unit_m_vs_millas_and_legal_zone_limits():
    sc = next(s for s in SCENARIOS_30 if s["case_id"] == "TC-ADV-027")
    ev = _make_ev(sc)
    txt, findings = validate_with_spans(sc["adversarial_llm_text"], ev)
    assert [f["rule_id"] for f in findings] == ["SEM-ZONE-001"]
    assert findings[0]["matched_text"] == "12 millas"
    assert _slice_u16(txt, findings[0]["char_start"], findings[0]["char_end"]) == "12 millas"


def test_f3_sentence_negation_suppresses_semantic_rules():
    sc_incursion = SCENARIOS_30[0]  # DARK_VESSEL inside EEZ
    ev_inc = _make_ev(sc_incursion)
    negated = (
        "La conducta es incompatible con submarino militar y no constituye paso inocente "
        "ni navegación normal, sin ingresar a las 12 millas de mar territorial."
    )
    _, findings = validate_with_spans(negated, ev_inc)
    assert findings == []

    sc_coop = next(s for s in SCENARIOS_30 if s["case_id"] == "TC-ADV-030")
    ev_coop = _make_ev(sc_coop)
    _, findings_coop = validate_with_spans("Se descarta piratería marítima al contar con licencia.", ev_coop)
    assert findings_coop == []


def test_f4_rcs_validation():
    sc = SCENARIOS_30[0]  # peak_rcs_db=51.6
    ev = _make_ev(sc)
    _, ok_findings = validate_with_spans("Eco radar de +51.6 dB confirmado.", ev)
    assert ok_findings == []

    txt, bad_findings = validate_with_spans("Eco radar débil de 18.0 dB atribuible a boya.", ev)
    assert len(bad_findings) == 1
    assert bad_findings[0]["rule_id"] == "NUM-RCS-001"
    assert bad_findings[0]["expected"] == 51.6
    assert bad_findings[0]["observed"] == 18.0
    assert _slice_u16(txt, bad_findings[0]["char_start"], bad_findings[0]["char_end"]) == "18.0 dB"


def test_f5_trimmed_spans_and_all_8_adversarial_probes():
    for sc in SCENARIOS_30:
        if "adversarial_llm_text" not in sc:
            continue
        ev = _make_ev(sc, use_flags=True)
        res = validate_legal_narrative(sc["adversarial_llm_text"], ev)
        assert not res.is_valid, f"Expected adversarial probe {sc['case_id']} to be flagged"
        for f in res.findings:
            assert f["matched_text"] == f["matched_text"].strip()
            assert _slice_u16(res.sanitized_legal_text, f["char_start"], f["char_end"]) == f["matched_text"]


def test_sam_pipeline_bbox_and_dry_run(tmp_path):
    import asyncio
    import numpy as np
    from app.processing.morphology import extract_sar_targets, export_sar_chip_png
    from app.laya.meta_muse_engine import segment_sar_chip_with_box_prompt

    mask = np.zeros((100, 100), dtype=bool)
    mask[48:54, 49:53] = True
    intensity = np.ones((100, 100), dtype=np.float32)
    intensity[48:54, 49:53] = 500.0

    dets = extract_sar_targets(mask, intensity)
    assert len(dets) == 1
    assert dets[0].bbox_crop_px is not None
    assert len(dets[0].bbox_crop_px) == 4

    chip_file = str(tmp_path / "chip_test.png")
    vv_db = 10.0 * np.log10(intensity)
    meta = export_sar_chip_png(vv_db, vv_db - 5.0, 18, 82, 18, 82, chip_file)
    assert meta["width"] == 64 and meta["height"] == 64
    assert len(meta["sha256"]) == 64

    dry = asyncio.run(
        segment_sar_chip_with_box_prompt(
            chip_file,
            bbox_xyxy=dets[0].bbox_crop_px,
            text_prompt="ship",
            dry_run=True,
        )
    )
    assert dry["mode"] == "dry_run"
    assert dry["api_calls_made"] == 0
    assert dry["request_payload"]["model"] == "sam-3.1"
    assert dry["request_payload"]["metadata"]["box_prompt_xyxy"] == dets[0].bbox_crop_px
