"""ChronoVisage web API.

Run from the backend/ folder:
    uvicorn api:app --host 0.0.0.0 --port 8000
UI work without the GPU models (fake results):
    CV_PIPELINE=stub uvicorn api:app --port 8000

Built on Starlette, the framework FastAPI runs on: same uvicorn command, same
routes the game plan lists, and nothing extra to install on the Mac.

Routes
  GET  /health                         pipeline mode, queue length
  GET  /metrics                        segmenter IoU etc. from metrics.json
  GET  /demos                          the preloaded demo photos
  POST /restore                        file (or key) [+ mask] [+ fidelity] -> job
  POST /colorize                      key [+ fidelity] -> colour version + guess map
  GET  /jobs/{id}                      job status; includes the result when done
  GET  /results/{key}?fidelity=0.7     result JSON if it is cached, else 404
  GET  /results/{key}/{artifact}       any cached file (add ?download=1 to save it)
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import queue
import shutil
import threading
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import restore_hook as hook

HERE = Path(__file__).resolve().parent
# Test mode keeps its fake results in a separate folder, so they can never be served as real ones.
_DEFAULT_CACHE = HERE.parent / ("cache_stub" if os.environ.get("CV_PIPELINE") == "stub" else "cache")
CACHE = Path(os.environ.get("CV_CACHE", _DEFAULT_CACHE)).resolve()
DEMOS = Path(os.environ.get("CV_DEMOS", HERE / "demos")).resolve()
METRICS = HERE / "metrics.json"
FRONTEND_DIST = Path(os.environ.get("CV_SITE", HERE.parent / "frontend" / "dist")).resolve()

FIDELITY_STEPS = (0.3, 0.7, 1.0)
DEFAULT_FIDELITY = 0.7
MAX_UPLOAD = 30 * 1024 * 1024
KEY_CHARS = set("0123456789abcdef")


def now() -> float:
    return time.time()


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


# --------------------------------------------------------------------------- #
# Bringing an image into the cache
# --------------------------------------------------------------------------- #
def _normalise_image(data: bytes) -> Image.Image:
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("That file isn't an image we can read (try JPG or PNG).") from e
    img = ImageOps.exif_transpose(img)  # phone photos of prints are often rotated
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):  # 16-bit scans
        arr = np.asarray(img, dtype=np.float64)
        arr = (arr - arr.min()) / max(arr.max() - arr.min(), 1) * 255
        img = Image.fromarray(arr.astype(np.uint8), mode="L")
    elif img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def _normalise_mask(data: bytes, size: tuple[int, int]) -> bytes:
    """Any mask image -> PNG, same size as the photo, white = damaged."""
    try:
        m = Image.open(io.BytesIO(data))
        m.load()
    except (UnidentifiedImageError, OSError) as e:
        raise ValueError("The mask isn't a readable image.") from e
    if m.mode in ("RGBA", "LA"):
        # Painted masks: anything drawn (opaque) counts, transparent does not
        alpha = np.asarray(m.getchannel("A"))
        lum = np.asarray(m.convert("L"))
        arr = ((alpha > 127) & (lum > 127)).astype(np.uint8) * 255
    else:
        arr = (np.asarray(m.convert("L")) > 127).astype(np.uint8) * 255
    out = Image.fromarray(arr, mode="L")
    if out.size != size:
        out = out.resize(size, Image.NEAREST)
    buf = io.BytesIO()
    out.save(buf, format="PNG")
    return buf.getvalue()


def ingest(image_bytes: bytes, *, filename: str, mask_bytes: bytes | None = None,
           mask_source: str | None = None, faces_json: bytes | None = None,
           kind: str = "photo") -> str:
    """Save the photo (and mask) as cache/<key>/input.png (+ input_mask.png).

    key = SHA-256 of the photo, or of photo + mask when a mask is supplied, so a
    re-painted mask gets its own results instead of overwriting the old ones.
    """
    sha = hashlib.sha256(image_bytes).hexdigest()
    img = _normalise_image(image_bytes)
    mask_png = _normalise_mask(mask_bytes, img.size) if mask_bytes else None
    key = sha if mask_png is None else hashlib.sha256(image_bytes + b"\0mask\0" + mask_png).hexdigest()
    if kind == "document":  # documents get their own results, made by the document path
        key = hashlib.sha256(image_bytes + b"\0document\0" + (mask_png or b"")).hexdigest()

    folder = CACHE / key
    if (folder / "source.json").exists():
        return key
    tmp = CACHE / f".{key}.{uuid.uuid4().hex[:6]}"
    tmp.mkdir(parents=True)
    img.save(tmp / "input.png")
    if mask_png is not None:
        (tmp / "input_mask.png").write_bytes(mask_png)
    if faces_json is not None:
        (tmp / "input_faces.json").write_bytes(faces_json)
    thumb = img.convert("RGB")
    thumb.thumbnail((640, 640))
    thumb.save(tmp / "thumb.jpg", quality=85)
    (tmp / "source.json").write_text(json.dumps({
        "sha256": sha,
        "filename": filename,
        "mask_source": mask_source if mask_png is not None else "segmenter",
        "kind": kind,
        "width": img.size[0],
        "height": img.size[1],
        "ingested_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, indent=2))
    try:
        tmp.rename(folder)
    except OSError:  # someone else ingested the same photo at the same moment
        shutil.rmtree(tmp, ignore_errors=True)
    return key


def valid_key(key: str) -> bool:
    return len(key) == 64 and set(key) <= KEY_CHARS and (CACHE / key / "source.json").exists()


def cached_result(key: str, fidelity: float) -> dict | None:
    f = hook.fidelity_dir(CACHE / key, fidelity) / "result.json"
    return json.loads(f.read_text()) if f.exists() else None


def parse_fidelity(raw) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise ValueError("fidelity must be a number between 0 and 1")
    if not 0.0 <= v <= 1.0:
        raise ValueError("fidelity must be between 0 and 1")
    return round(v, 2)


# --------------------------------------------------------------------------- #
# One-at-a-time job queue
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    id: str
    key: str
    fidelity: float
    status: str = "queued"          # queued | running | done | error
    error: str | None = None
    detail: str | None = None
    created: float = field(default_factory=now)
    started: float | None = None
    finished: float | None = None


JOBS: dict[str, Job] = {}
ACTIVE: dict[tuple[str, float], str] = {}  # (key, fidelity) -> job id still queued/running
LOCK = threading.Lock()
WORK: "queue.Queue[str]" = queue.Queue()


def enqueue(key: str, fidelity: float) -> Job:
    with LOCK:
        if cached_result(key, fidelity):
            job = Job(id=uuid.uuid4().hex, key=key, fidelity=fidelity, status="done",
                      started=now(), finished=now())
            JOBS[job.id] = job
            return job
        existing = ACTIVE.get((key, fidelity))
        if existing:
            return JOBS[existing]
        job = Job(id=uuid.uuid4().hex, key=key, fidelity=fidelity)
        JOBS[job.id] = job
        ACTIVE[(key, fidelity)] = job.id
    WORK.put(job.id)
    return job


def queue_position(job: Job) -> int | None:
    if job.status != "queued":
        return None
    with LOCK:
        waiting = [j for j in JOBS.values() if j.status == "queued"]
    waiting.sort(key=lambda j: j.created)
    return next((i + 1 for i, j in enumerate(waiting) if j.id == job.id), None)


def worker() -> None:
    while True:
        job_id = WORK.get()
        job = JOBS[job_id]
        job.status, job.started = "running", now()
        try:
            folder = CACHE / job.key
            source = json.loads((folder / "source.json").read_text())
            is_demo = any(d["key"] == job.key for d in DEMO_INDEX)
            hook.run_restore(folder / "input.png", job.fidelity, source,
                             seeds=hook.DEMO_SEEDS if is_demo else None)
            job.status = "done"
        except Exception as e:  # report it to the page instead of killing the worker
            job.status = "error"
            job.error = f"{type(e).__name__}: {e}"
            job.detail = traceback.format_exc()[-4000:]
            print(f"[job {job.id[:8]}] failed:\n{job.detail}", flush=True)
        finally:
            job.finished = now()
            with LOCK:
                ACTIVE.pop((job.key, job.fidelity), None)
            WORK.task_done()


def job_json(job: Job) -> dict:
    out = {
        "id": job.id,
        "key": job.key,
        "fidelity": job.fidelity,
        "status": job.status,
        "position": queue_position(job),
        "error": job.error,
        "detail": job.detail,
        "elapsed": round((job.finished or now()) - (job.started or job.created), 1),
    }
    if job.status == "done":
        out["result"] = cached_result(job.key, job.fidelity)
    return out


# --------------------------------------------------------------------------- #
# Demo photos
# --------------------------------------------------------------------------- #
DEMO_INDEX: list[dict] = []


def load_demos(warm: bool) -> None:
    """Ingest every photo listed in demos/demos.json and, if `warm`, queue any
    fidelity step that isn't cached yet (0.7 first, so a card works soonest)."""
    DEMO_INDEX.clear()
    listing = DEMOS / "demos.json"
    if not listing.exists():
        return
    for entry in json.loads(listing.read_text()):
        path = DEMOS / entry["file"]
        if not path.exists():
            print(f"[demos] missing {path.name}; skipped", flush=True)
            continue
        mask = path.with_name(path.stem + "_mask.png")
        faces = path.with_name(path.stem + "_faces.json")
        key = ingest(path.read_bytes(), filename=path.name,
                     mask_bytes=mask.read_bytes() if mask.exists() else None,
                     mask_source="human_file",
                     faces_json=faces.read_bytes() if faces.exists() else None,
                     kind=entry.get("kind", "photo"))
        DEMO_INDEX.append({**entry, "key": key})
    if warm:
        for fid in (DEFAULT_FIDELITY, *[f for f in FIDELITY_STEPS if f != DEFAULT_FIDELITY]):
            for d in DEMO_INDEX:
                enqueue(d["key"], fid)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
async def health(request: Request):
    return JSONResponse({
        "ok": True,
        "pipeline": hook.pipeline_name(),
        "queued": sum(1 for j in JOBS.values() if j.status == "queued"),
        "running": sum(1 for j in JOBS.values() if j.status == "running"),
        "fidelity_steps": FIDELITY_STEPS,
    })


async def metrics(request: Request):
    if not METRICS.exists():
        return JSONResponse({})
    return JSONResponse(json.loads(METRICS.read_text()))


async def demos(request: Request):
    out = []
    for d in DEMO_INDEX:
        ready = [f for f in FIDELITY_STEPS if cached_result(d["key"], f)]
        out.append({**d, "thumb": "thumb.jpg", "ready": ready})
    return JSONResponse(out)


async def restore_route(request: Request):
    try:
        form = await request.form(max_files=2, max_fields=10, max_part_size=MAX_UPLOAD)
    except Exception as e:
        return error(400, f"Couldn't read the upload: {e}")

    try:
        fidelity = parse_fidelity(form.get("fidelity", DEFAULT_FIDELITY))
    except ValueError as e:
        return error(400, str(e))
    want_all = str(form.get("all_fidelities", "true")).lower() in {"1", "true", "yes"}

    upload, mask_upload = form.get("file"), form.get("mask")
    kind = "document" if str(form.get("kind", "")).lower() == "document" else "photo"
    mask_bytes = await mask_upload.read() if hasattr(mask_upload, "read") else None
    if mask_bytes == b"":
        mask_bytes = None

    try:
        if hasattr(upload, "read"):
            data = await upload.read()
            if not data:
                return error(400, "The uploaded file is empty.")
            if len(data) > MAX_UPLOAD:
                return error(413, "That photo is over 30 MB; please export a smaller copy.")
            key = await run_in_threadpool(ingest, data, filename=upload.filename or "upload",
                                          mask_bytes=mask_bytes, mask_source="human_brush", kind=kind)
        elif form.get("key"):
            base = str(form.get("key"))
            if not valid_key(base):
                return error(404, "Unknown photo key.")
            if mask_bytes is None:
                key = base
            else:  # same photo, new hand-painted mask
                src = CACHE / base
                original = json.loads((src / "source.json").read_text())
                kind = original.get("kind", kind)
                faces = src / "input_faces.json"
                key = await run_in_threadpool(
                    ingest, (src / "input.png").read_bytes(), filename=original["filename"],
                    mask_bytes=mask_bytes, mask_source="human_brush",
                    faces_json=faces.read_bytes() if faces.exists() else None, kind=kind)
        else:
            return error(400, "Send a photo as 'file' (or the 'key' of one already uploaded).")
    except ValueError as e:
        return error(400, str(e))

    job = enqueue(key, fidelity)
    if want_all:
        for f in FIDELITY_STEPS:
            if f != fidelity:
                enqueue(key, f)
    return JSONResponse(job_json(job), status_code=202 if job.status != "done" else 200)


async def job_route(request: Request):
    job = JOBS.get(request.path_params["job_id"])
    if not job:
        return error(404, "No such job (the server may have restarted; try again).")
    return JSONResponse(job_json(job))


async def result_route(request: Request):
    key = request.path_params["key"]
    if not valid_key(key):
        return error(404, "Unknown photo key.")
    try:
        fidelity = parse_fidelity(request.query_params.get("fidelity", DEFAULT_FIDELITY))
    except ValueError as e:
        return error(400, str(e))
    result = cached_result(key, fidelity)
    if result is None:
        # 202, not 404: the photo exists, this step just isn't computed (yet)
        pending = ACTIVE.get((key, fidelity))
        return JSONResponse({"status": "pending" if pending else "missing", "job_id": pending},
                            status_code=202)
    return JSONResponse(result)


async def propose_route(request: Request):
    """Upload a photo and get the segmenter's proposed damage mask, for review in the brush."""
    try:
        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_UPLOAD)
    except Exception as e:
        return error(400, f"Couldn't read the upload: {e}")
    upload = form.get("file")
    if not hasattr(upload, "read"):
        return error(400, "Send a photo as 'file'.")
    data = await upload.read()
    if not data:
        return error(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD:
        return error(413, "That photo is over 30 MB; please export a smaller copy.")
    try:
        kind = "document" if str(form.get("kind", "")).lower() == "document" else "photo"
        key = await run_in_threadpool(ingest, data, filename=upload.filename or "upload", kind=kind)
    except ValueError as e:
        return error(400, str(e))
    try:
        await run_in_threadpool(hook.propose_mask, CACHE / key / "input.png", kind)
        mask = "proposed_mask.png"
    except Exception as e:  # the brush still works from a blank mask
        print(f"[propose] {key[:8]} failed: {type(e).__name__}: {e}", flush=True)
        mask = None
    return JSONResponse({"key": key, "original": "input.png", "mask": mask})


async def artifact_route(request: Request):
    key, artifact = request.path_params["key"], request.path_params["artifact"]
    if not valid_key(key):
        return error(404, "Unknown photo key.")
    folder = (CACHE / key).resolve()
    path = (folder / artifact).resolve()
    if folder not in path.parents or not path.is_file():
        return error(404, "No such file.")
    download = request.query_params.get("download") in {"1", "true"}
    headers = {"Cache-Control": "public, max-age=31536000, immutable"}
    if download:
        name = f"coldcase_{key[:8]}_{artifact.replace('/', '_')}"
        return FileResponse(path, filename=name, headers=headers)
    return FileResponse(path, headers=headers)


async def colorize_route(request: Request):
    """Colour mode: add colour to a cached restoration (POST key, fidelity). Takes ~2 s."""
    try:
        form = await request.form(max_files=0, max_fields=4)
    except Exception as e:
        return error(400, f"Couldn't read the request: {e}")
    key = str(form.get("key", ""))
    if not valid_key(key) or not (CACHE / key).is_dir():
        return error(404, "Unknown photo key.")
    try:
        fidelity = parse_fidelity(form.get("fidelity", DEFAULT_FIDELITY))
    except ValueError as e:
        return error(400, str(e))
    folder = hook.fidelity_dir(CACHE / key, fidelity)
    src = folder / "restored.png"
    if not src.is_file():
        return error(409, "Restore the photo first; colour is added to the restoration.")
    try:
        import colorize
        meta = await run_in_threadpool(colorize.colorize_file, src, folder / "color",
                                       hook.sign_c2pa if hook.pipeline_name() == "real" else None,
                                       hook.map_png)
    except ValueError as e:
        return error(422, str(e))
    except Exception as e:
        traceback.print_exc()
        return error(500, f"Colouring failed: {type(e).__name__}: {e}")
    return JSONResponse(meta)


def preload_models() -> None:
    """Load the segmenter, SDXL and CodeFormer once at startup, so the first visitor's
    upload doesn't wait 20-40 s for model loading. Failures are logged, not fatal."""
    t0 = time.time()
    for name, load in (("segmenter", "pipeline.segment:get_model"),
                       ("SDXL", "pipeline.inpaint:get_pipe"),
                       ("CodeFormer", "pipeline.codeformer:get_net"),
                       ("colorizers", "colorize:get_models")):
        try:
            mod, fn = load.split(":")
            getattr(__import__(mod, fromlist=[fn]), fn)()
        except Exception as e:
            print(f"[preload] {name} failed: {type(e).__name__}: {e}", flush=True)
    print(f"[preload] models ready in {time.time() - t0:.0f}s", flush=True)


@asynccontextmanager
async def lifespan(app):
    CACHE.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, name="restore-worker", daemon=True).start()
    if hook.pipeline_name() == "real" and os.environ.get("CV_PRELOAD", "1") != "0":
        threading.Thread(target=preload_models, name="preload", daemon=True).start()
    await run_in_threadpool(load_demos, os.environ.get("CV_WARM_DEMOS", "1") != "0")
    print(f"[chronovisage] pipeline={hook.pipeline_name()} cache={CACHE} demos={len(DEMO_INDEX)}", flush=True)
    yield


routes = [
    Route("/health", health),
    Route("/metrics", metrics),
    Route("/demos", demos),
    Route("/restore", restore_route, methods=["POST"]),
    Route("/propose", propose_route, methods=["POST"]),
    Route("/colorize", colorize_route, methods=["POST"]),
    Route("/jobs/{job_id}", job_route),
    Route("/results/{key}", result_route),
    Route("/results/{key}/{artifact:path}", artifact_route),
]
if FRONTEND_DIST.is_dir():  # serve the built site too, so one tunnel URL is enough
    routes.append(Mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="site"))

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[Middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in os.environ.get("CV_ALLOWED_ORIGINS", "*").split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )],
)
