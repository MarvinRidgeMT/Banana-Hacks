import json
import numpy as np
from datetime import datetime, timezone
from .invention_map import EPS, TAU

TOOL = "ChronoVisage 0.1"

def build_manifest(r):
    """The edit manifest: an honest record of what the pipeline did to this photo."""
    outside = int(((r["original"] != r["restored"]).any(-1) & ~r["mask"]).sum())
    return {
        "source_sha256": r["sha256"],
        "tool": TOOL,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stages": [
            {"stage": "damage_segmentation", "model": r["mask_source"], "threshold": 0.5,
             "dilation_px": 4, "human_edited_mask": False,
             "damage_pixels": int(r["damage_mask"].sum())},
            *r["log"].summary(),
        ],
        "invention_map": {
            "method": "per-pixel seed spread in CIELAB lightness, Gaussian-smoothed (2 px)",
            "epsilon_lab": EPS, "tau_lightness": TAU,
            "classes": {"0": "observed (original pixel, untouched)",
                        "1": "inferred (regenerated, seeds agree)",
                        "2": "invented (regenerated, seeds disagree)"},
            "caveat": "Seed agreement measures how constrained the model was, not whether it is correct.",
        },
        "pixel_summary": r["pixel_summary"],
        "regions": r["regions"],
        "untouched_pixel_check": "pass" if outside == 0 else f"fail ({outside} px)",
    }

def write_manifest(r, path):
    with open(path, "w") as f:
        json.dump(build_manifest(r), f, indent=2)
