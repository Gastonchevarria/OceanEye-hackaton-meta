#!/usr/bin/env python3
"""CI Integrity Gate for OceanEye Sentinel 2.0 (Meta AI Hackathon)."""
import os, sys, json, re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    errors = []
    # 1. Verify byte-identical sync between frontend/ and docs/
    for a, b in [
        ("frontend/index.html", "docs/index.html"),
        ("frontend/app/index.html", "docs/app/index.html"),
    ]:
        if open(os.path.join(REPO, a), "rb").read() != open(os.path.join(REPO, b), "rb").read():
            errors.append(f"Out of sync: {a} != {b}")

    # 2. Verify zero forbidden overclaims or legacy strings in HTML/PY/MD
    for rel in ["frontend/index.html", "frontend/app/index.html", "README.md"]:
        txt = open(os.path.join(REPO, rel)).read()
        if "PODER JUDICIAL DE LA NACIÓN" in txt:
            errors.append(f"Forbidden judicial header found in {rel}")
        if re.search(r"\b(bbva|leonardo)\b", txt, re.I):
            errors.append(f"Forbidden legacy string found in {rel}")
        if 'href="/app"' in txt:
            errors.append(f"Root-absolute /app link found in {rel}")
        if "DARK-VV-VH-001" in txt:
            errors.append(f"Non-existent DARK-VV-VH-001 target ID found in {rel}")

    # 3. Verify stats.json, sam_masks.json, arena_replay.json exist and match benchmark
    for fn in ["stats.json", "sam_masks.json", "arena_replay.json", "meta_muse_sam31_benchmark_2026.json"]:
        p = os.path.join(REPO, "docs/data", fn)
        if not os.path.exists(p):
            errors.append(f"Missing artifact: docs/data/{fn}")

    if errors:
        for e in errors:
            print("ERROR:", e)
        sys.exit(1)
    print("INTEGRITY CHECK PASSED: 0 errors.")

if __name__ == "__main__":
    main()
