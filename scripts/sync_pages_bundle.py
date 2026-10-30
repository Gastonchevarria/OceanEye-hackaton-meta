#!/usr/bin/env python3
"""Synchronize single source of truth from frontend/index.html, frontend/app/index.html, and frontend/data/ into docs/, root, and backend/data/."""
import os
import shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def copy_tree_contents(src_dir: str, dst_dir: str) -> None:
    os.makedirs(dst_dir, exist_ok=True)
    for entry in os.listdir(src_dir):
        if entry in (".DS_Store", "__pycache__", ".vercel"):
            continue
        s = os.path.join(src_dir, entry)
        d = os.path.join(dst_dir, entry)
        if os.path.isdir(s):
            copy_tree_contents(s, d)
        elif os.path.isfile(s):
            shutil.copyfile(s, d)


def main() -> None:
    # 1. Source of truth: frontend/index.html -> docs/index.html, index.html
    src_landing = os.path.join(REPO, "frontend", "index.html")
    for dst in ("docs/index.html", "index.html"):
        dst_path = os.path.join(REPO, dst)
        os.makedirs(os.path.dirname(dst_path) or REPO, exist_ok=True)
        shutil.copyfile(src_landing, dst_path)

    # 2. Source of truth: frontend/app/index.html -> docs/app/index.html, app/index.html, frontend/app.html, docs/app.html, app.html
    src_app = os.path.join(REPO, "frontend", "app", "index.html")
    for dst in ("docs/app/index.html", "app/index.html", "frontend/app.html", "docs/app.html", "app.html"):
        dst_path = os.path.join(REPO, dst)
        os.makedirs(os.path.dirname(dst_path) or REPO, exist_ok=True)
        shutil.copyfile(src_app, dst_path)

    # 3. Source of truth: frontend/data/ (including sam_chips/) -> docs/data/, data/, and backend/data/stats.json
    src_data = os.path.join(REPO, "frontend", "data")
    for dst_dir in ("docs/data", "data"):
        copy_tree_contents(src_data, os.path.join(REPO, dst_dir))

    stats_src = os.path.join(src_data, "stats.json")
    backend_data_dir = os.path.join(REPO, "backend", "data")
    if os.path.isfile(stats_src) and os.path.isdir(backend_data_dir):
        shutil.copyfile(stats_src, os.path.join(backend_data_dir, "stats.json"))

    nojekyll = os.path.join(REPO, "docs", ".nojekyll")
    if not os.path.exists(nojekyll):
        open(nojekyll, "w", encoding="utf-8").close()

    print("Synced frontend/ -> docs/ and root bundle successfully.")


if __name__ == "__main__":
    main()
