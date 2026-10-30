#!/usr/bin/env python3
"""
OceanEye Sentinel 2.0 — Automated Integrity & Honesty Verification Suite
Implements specs/stats/README.md Section 2 + specs/pitch/pitch_90s.md checklist.
"""

import glob
import hashlib
import json
import os
import re
import site
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.append(site.getusersitepackages())

import build_stats  # noqa: E402


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_dot_path(obj, path_str: str):
    """Resolve simple dot/wildcard path on dict/list for source_path verification."""
    p = path_str
    if p.startswith("$."):
        p = p[2:]
    elif p.startswith("stats:"):
        p = p[len("stats:"):]
    # Handle bracket indexing like pricing.models["muse-wonder-1.0"]
    p = re.sub(r'\["([^"]+)"\]', r'.\1', p)
    p = re.sub(r"\[\*\]", ".*", p)
    parts = [x for x in p.split(".") if x]

    def _walk(curr, idx):
        if idx >= len(parts):
            return True
        part = parts[idx]
        if part == "*":
            if isinstance(curr, dict):
                return bool(curr) and all(_walk(v, idx + 1) for v in curr.values())
            if isinstance(curr, list):
                return bool(curr) and all(_walk(v, idx + 1) for v in curr)
            return False
        if "/" in part and idx == len(parts) - 1:
            subparts = part.split("/")
            return isinstance(curr, dict) and all(sp in curr for sp in subparts)
        if isinstance(curr, dict) and part in curr:
            return _walk(curr[part], idx + 1)
        return False

    return _walk(obj, 0)


def iter_source_paths(node):
    if isinstance(node, dict):
        if "source_path" in node and "formula" in node:
            sp = node["source_path"]
            if isinstance(sp, list):
                for item in sp:
                    yield item
            elif isinstance(sp, str):
                yield sp
        for v in node.values():
            yield from iter_source_paths(v)
    elif isinstance(node, list):
        for item in node:
            yield from iter_source_paths(item)


def main() -> int:
    errors = []
    warnings = []

    artifact_path = ROOT / "backend/ml/meta_muse_sam31_benchmark_2026.json"
    stats_fe = ROOT / "frontend/data/stats.json"
    stats_docs = ROOT / "docs/data/stats.json"
    stats_root = ROOT / "data/stats.json"

    if not artifact_path.exists():
        print(f"ERROR: missing artifact {artifact_path}")
        return 1
    if not stats_fe.exists():
        print(f"ERROR: missing {stats_fe}")
        return 1

    # 1. Recalcular y comparar stats.json
    stats_on_disk = json.loads(stats_fe.read_text(encoding="utf-8"))
    art_data, art_sha = build_stats.load_artifact(str(artifact_path))
    gen_at = stats_on_disk.get("provenance", {}).get("generated_at")
    src_commit = stats_on_disk.get("provenance", {}).get("source_commit")

    sam_masks_arg = None
    sam_masks_path = ROOT / "docs/data/sam_masks.json"
    if sam_masks_path.exists():
        sm_candidate = json.loads(sam_masks_path.read_text(encoding="utf-8"))
        if (sm_candidate.get("run") or {}).get("mode") == "live":
            sam_masks_arg = sm_candidate

    recomputed = build_stats.build(
        art_data,
        art_sha,
        artifact_path.name,
        repo_root=str(ROOT),
        source_commit=src_commit,
        generated_at=gen_at,
        sam_masks=sam_masks_arg,
    )

    if recomputed != stats_on_disk:
        errors.append("stats.json on disk differs from recomputed build_stats.py output")

    rec_sha = stats_on_disk.get("provenance", {}).get("artifact", {}).get("sha256")
    if rec_sha != art_sha:
        errors.append(f"provenance.artifact.sha256 ({rec_sha}) != real artifact sha256 ({art_sha})")

    # 2. Integridad
    blocking = stats_on_disk.get("integrity", {}).get("blocking_failures", -1)
    if blocking != 0:
        errors.append(f"integrity.blocking_failures is {blocking} (expected 0)")

    known = [
        c for c in stats_on_disk.get("integrity", {}).get("checks", [])
        if c.get("ok") is False and c.get("severity") != "error"
    ]
    print(f"integrity.known_inconsistencies: {len(known)}")
    for c in known:
        print(f"  - [{c['id']}] ({c['severity']}): {c.get('note') or c.get('description')}")

    # 3. Afirmaciones prohibidas (forbidden_claims)
    forbidden = stats_on_disk.get("forbidden_claims", [])
    # Scan stats.json excluding forbidden_claims
    stats_body = {k: v for k, v in stats_on_disk.items() if k != "forbidden_claims"}
    for path_str, text_val in build_stats.iter_strings(stats_body):
        for fc in forbidden:
            flags = re.IGNORECASE if "i" in fc.get("flags", "") else 0
            if re.search(fc["pattern"], text_val, flags):
                msg = f"stats.json:{path_str}:{fc['id']}"
                if fc.get("severity") == "error":
                    errors.append(msg)
                else:
                    warnings.append(msg)

    # Scan frontend/**/*.html|js|json
    fe_files = sorted(
        set(
            glob.glob(str(ROOT / "frontend/**/*.html"), recursive=True)
            + glob.glob(str(ROOT / "frontend/**/*.js"), recursive=True)
            + glob.glob(str(ROOT / "frontend/**/*.json"), recursive=True)
        )
    )
    for fpath in fe_files:
        p = Path(fpath)
        rel = p.relative_to(ROOT).as_posix()
        # Skip raw benchmark artifact & arena_replay data_quality notes if json
        if p.name in ("meta_muse_sam31_benchmark_2026.json", "arena_replay.json"):
            continue
        lines = p.read_text(encoding="utf-8").splitlines()
        for fc in forbidden:
            applies = fc.get("applies_to", [])
            ext_ok = any(rel.endswith(a.split("*")[-1]) for a in applies)
            if not ext_ok:
                continue
            flags = re.IGNORECASE if "i" in fc.get("flags", "") else 0
            rx = re.compile(fc["pattern"], flags)
            for idx, line in enumerate(lines, start=1):
                # In stats.json skip the forbidden_claims block itself
                if p.name == "stats.json":
                    continue
                if rx.search(line):
                    hit = f"{rel}:{idx}:{fc['id']}"
                    if fc.get("severity") == "error":
                        errors.append(hit)
                    else:
                        warnings.append(hit)

    # Pitch checklist extra hard-coded strings in frontend/app/index.html & frontend/index.html
    pitch_forbidden_literals = [
        ("pitch-onnx-92-3", r"92[.,]3\s*%\s*P\(BUQUE\)|92[.,]34\s*%\s*P\(Buque"),
        ("pitch-esa-copernicus", r"ESA\s+COPERNICUS"),
    ]
    for html_rel in ("frontend/index.html", "frontend/app/index.html"):
        hp = ROOT / html_rel
        if hp.exists():
            for idx, line in enumerate(hp.read_text(encoding="utf-8").splitlines(), start=1):
                for pid, pat in pitch_forbidden_literals:
                    if re.search(pat, line, re.IGNORECASE):
                        errors.append(f"{html_rel}:{idx}:{pid}")

    # 4. Referencias source_path
    sam_completed = (
        stats_on_disk.get("sam", {})
        .get("real_sar_inspector", {})
        .get("status", {})
        .get("value")
        == "completed"
    )
    for sp in iter_source_paths(stats_body):
        if sp.startswith("$."):
            if not resolve_dot_path(art_data, sp):
                errors.append(f"Unresolved artifact source_path: {sp}")
        elif sp.startswith("stats:"):
            if not resolve_dot_path(stats_on_disk, sp):
                errors.append(f"Unresolved stats source_path: {sp}")
        elif sp.startswith("file:sam_masks.json#"):
            if sam_completed:
                sub = sp.split("#", 1)[1]
                if not sam_masks_path.exists() or not resolve_dot_path(
                    json.loads(sam_masks_path.read_text(encoding="utf-8")), sub
                ):
                    errors.append(f"Unresolved sam_masks source_path: {sp}")
        elif sp.startswith("code:"):
            code_file = sp[len("code:"):].split(":")[0]
            if not (ROOT / code_file).exists():
                errors.append(f"Missing code file in source_path: {sp}")

    # 5. Espejos byte a byte (data/, docs/data/, frontend/data/ y HTMLs)
    for fname in ("stats.json", "arena_replay.json", "sam_masks.json"):
        paths = [ROOT / "frontend/data" / fname, ROOT / "docs/data" / fname, ROOT / "data" / fname]
        if not all(x.exists() for x in paths):
            errors.append(f"Missing mirror copy for {fname}")
        else:
            b0 = paths[0].read_bytes()
            for m in paths[1:]:
                if m.read_bytes() != b0:
                    errors.append(f"Mirror mismatch: {m.relative_to(ROOT)} != frontend/data/{fname}")

    # sam_chips mirrors if present
    fe_chips_dir = ROOT / "frontend/data/sam_chips"
    if fe_chips_dir.exists():
        for chip in sorted(fe_chips_dir.glob("*.png")):
            for mirror_dir in (ROOT / "docs/data/sam_chips", ROOT / "data/sam_chips"):
                mc = mirror_dir / chip.name
                if not mc.exists() or mc.read_bytes() != chip.read_bytes():
                    errors.append(f"Mirror mismatch for sam_chips/{chip.name} in {mirror_dir}")

    for html_sub in ("index.html", "app/index.html"):
        h_paths = [ROOT / "frontend" / html_sub, ROOT / "docs" / html_sub, ROOT / html_sub]
        b0 = h_paths[0].read_bytes()
        for m in h_paths[1:]:
            if not m.exists() or m.read_bytes() != b0:
                errors.append(f"HTML mirror mismatch: {m.relative_to(ROOT)} != frontend/{html_sub}")

    # 6. Zero BBVA / Leonardo / seed leak in git
    git_log = subprocess.check_output(
        ["git", "-C", str(ROOT), "log", "--all", "--grep=BBVA", "--grep=Leonardo", "-i", "--oneline"],
        text=True,
    ).strip()
    if git_log:
        errors.append(f"Git log contains forbidden brand terms: {git_log}")

    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"  WARN: {w}")

    if errors:
        print(f"INTEGRITY CHECK FAILED ({len(errors)} errors):")
        for e in errors:
            print(f"  ERROR: {e}")
        return 1

    print("INTEGRITY CHECK PASSED: 0 errors")
    return 0


if __name__ == "__main__":
    sys.exit(main())
