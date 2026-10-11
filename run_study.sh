#!/bin/bash
# One command: switch to the website branch, bring in the pipeline, render the hero ("study") first.
set -e
cd ~/Banana-Hacks
source .venv/bin/activate
if pgrep -f render_demo.py >/dev/null; then echo "STOP: the couple/boy render is still running. Press Ctrl+C in its window first."; exit 1; fi
git fetch
git checkout website
git pull --no-edit
git merge main --no-edit -m "Merge latest pipeline from main"
cp ~/bh_demos/backend/demos/*_mask.png ~/bh_demos/backend/demos/*_faces.json backend/demos/ 2>/dev/null || true
cd backend
[ -e weights ] || ln -s ../weights weights
[ -e third_party ] || ln -s ../third_party third_party
pip install -q -r requirements-web.txt
caffeinate -i python ../training/render_study.py 2>&1 | grep -v "WARN\|warn\|deprecat\|it/s\|Loading"
