#!/usr/bin/env python3
"""Synchronize single source of truth from frontend/ into docs/ and root static bundle."""
import os, shutil

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    # Copy frontend/index.html -> docs/index.html and root index.html
    for dst in ["docs/index.html", "index.html"]:
        shutil.copyfile(os.path.join(REPO, "frontend/index.html"), os.path.join(REPO, dst))
    # Copy frontend/app/index.html -> docs/app/index.html, app/index.html, frontend/app.html, docs/app.html, app.html
    for dst in ["docs/app/index.html", "app/index.html", "frontend/app.html", "docs/app.html", "app.html"]:
        os.makedirs(os.path.dirname(os.path.join(REPO, dst)), exist_ok=True)
        shutil.copyfile(os.path.join(REPO, "frontend/app/index.html"), os.path.join(REPO, dst))
    # Sync data/ files
    src_data = os.path.join(REPO, "frontend/data")
    for dst_dir in ["docs/data", "data"]:
        full_dst = os.path.join(REPO, dst_dir)
        os.makedirs(full_dst, exist_ok=True)
        for fn in os.listdir(src_data):
            s = os.path.join(src_data, fn)
            if os.path.isfile(s):
                shutil.copyfile(s, os.path.join(full_dst, fn))
    print("Synced frontend/ -> docs/ and root bundle successfully.")

if __name__ == "__main__":
    main()
