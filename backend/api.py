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

import auth
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
MAX_PIXELS = 80_000_000          # ~ a 10,000 x 8,000 scan; larger is refused (decompression-bomb guard)
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
MAX_QUEUE = 300                  # waiting jobs; beyond this new uploads get a polite 503
MAX_BODY = {"/batch": 400 * 1024 * 1024}   # whole-request limits; everything else 40 MB
MAX_BODY_DEFAULT = 40 * 1024 * 1024
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
        if img.width * img.height > MAX_PIXELS:
            raise ValueError("That image is too large (over 80 megapixels); please export a smaller copy.")
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
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
        if m.width * m.height > MAX_PIXELS:
            raise ValueError("The mask is too large.")
        m.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
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
    """The cached result, but only if the current pipeline made it (older renders are redone)."""
    f = hook.fidelity_dir(CACHE / key, fidelity) / "result.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text())
    if r.get("pipeline", "stub") != hook.pipeline_name() or r.get("render_version") != hook.RENDER_VERSION:
        return None
    return r


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


def queue_full() -> bool:
    return WORK.qsize() >= MAX_QUEUE


async def restore_route(request: Request):
    if not auth.allow(client_ip(request), "upload", 40, 3600):
        return error(429, "Too many uploads from your network this hour. Try again later.")
    if queue_full():
        return error(503, "The restorer is very busy right now. Please try again in a few minutes.")
    try:
        form = await request.form(max_files=2, max_fields=10, max_part_size=MAX_UPLOAD)
    except Exception as e:
        return error(400, "Couldn't read the upload (one image, up to 30 MB).")

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
    if not auth.allow(client_ip(request), "upload", 40, 3600):
        return error(429, "Too many uploads from your network this hour. Try again later.")
    """Upload a photo and get the segmenter's proposed damage mask, for review in the brush."""
    try:
        form = await request.form(max_files=1, max_fields=4, max_part_size=MAX_UPLOAD)
    except Exception as e:
        return error(400, "Couldn't read the upload (one image, up to 30 MB).")
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


# --------------------------------------------------------------------------- #
# Accounts, per-user cases, rate limits
# --------------------------------------------------------------------------- #
def client_ip(request: Request) -> str:
    # behind the Cloudflare tunnel every request comes from localhost; Cloudflare passes the real IP
    peer = request.client.host if request.client else "?"
    if peer in ("127.0.0.1", "::1"):
        return request.headers.get("cf-connecting-ip") or peer
    return peer


def bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


def current_user(request: Request) -> dict | None:
    return auth.user_for(bearer(request))


async def _json_body(request: Request, limit: int = 4096) -> dict:
    raw = await request.body()
    if len(raw) > limit:
        raise ValueError("Request too large.")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        raise ValueError("Send JSON.")
    if not isinstance(body, dict):
        raise ValueError("Send a JSON object.")
    return body


async def signup_route(request: Request):
    if not auth.allow(client_ip(request), "auth", 10, 600):
        return error(429, "Too many attempts. Wait a few minutes and try again.")
    try:
        b = await _json_body(request)
        token, user = await run_in_threadpool(auth.signup, str(b.get("email", "")), str(b.get("password", "")), str(b.get("name", "")))
    except ValueError as e:
        return error(400, str(e))
    return JSONResponse({"token": token, "user": user})


async def login_route(request: Request):
    if not auth.allow(client_ip(request), "auth", 10, 600):
        return error(429, "Too many attempts. Wait a few minutes and try again.")
    try:
        b = await _json_body(request)
        token, user = await run_in_threadpool(auth.login, str(b.get("email", "")), str(b.get("password", "")))
    except ValueError as e:
        return error(401 if isinstance(e, auth.AuthError) else 400, str(e))
    return JSONResponse({"token": token, "user": user})


async def logout_route(request: Request):
    t = bearer(request)
    if t:
        await run_in_threadpool(auth.logout, t)
    return JSONResponse({"ok": True})


async def me_route(request: Request):
    u = current_user(request)
    if not u:
        return error(401, "Not signed in.")
    return JSONResponse({"email": u["email"], "name": u["name"]})


async def cases_route(request: Request):
    u = current_user(request)
    if not u:
        return error(401, "Sign in to see your cases.")
    if request.method == "GET":
        return JSONResponse(auth.list_cases(u["id"]))
    try:
        b = await _json_body(request)
    except ValueError as e:
        return error(400, str(e))
    key = str(b.get("key", ""))
    if b.get("action") == "delete":
        if key and not valid_key(key):
            return error(400, "Unknown photo key.")
        auth.remove_case(u["id"], key or None)
        return JSONResponse({"ok": True})
    if not valid_key(key) or not (CACHE / key).is_dir():
        return error(404, "Unknown photo key.")
    auth.add_case(u["id"], key, str(b.get("title", "")), str(b.get("kind", "photo")))
    return JSONResponse({"ok": True})


class BodyLimit:
    """Refuse oversized requests before they are read: by Content-Length, and by counting bytes
    for uploads that don't send one."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        limit = MAX_BODY.get(scope.get("path", ""), MAX_BODY_DEFAULT)
        for k, v in scope.get("headers", []):
            if k == b"content-length" and v.isdigit() and int(v) > limit:
                return await JSONResponse({"error": "That upload is too large."}, status_code=413)(scope, receive, send)
        seen = 0

        async def counted():
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > limit:
                    raise ValueError("request body too large")
            return msg
        await self.app(scope, counted, send)


class SecurityHeaders:
    """Hardening headers on every response."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapped(message):
            if message["type"] == "http.response.start":
                h = message.setdefault("headers", [])
                for k, v in ((b"x-content-type-options", b"nosniff"), (b"x-frame-options", b"DENY"),
                             (b"referrer-policy", b"no-referrer"),
                             (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                             (b"cross-origin-resource-policy", b"cross-origin"),
                             (b"strict-transport-security", b"max-age=31536000"),
                             (b"x-permitted-cross-domain-policies", b"none")):
                    h.append((k, v))
            await send(message)
        await self.app(scope, receive, send_wrapped)


# --------------------------------------------------------------------------- #
# Archive features: verify, likeness, typical-restorer comparison, catalog metadata, batch
# --------------------------------------------------------------------------- #
import csv
import features
from starlette.responses import PlainTextResponse, Response

FEATURE_LOCK = threading.Lock()   # CodeFormer / face models: one at a time
BATCHES = CACHE / "_batches"


def _result_or_404(key: str, fidelity: float):
    r = cached_result(key, fidelity) if valid_key(key) else None
    return r


async def _form(request: Request, files: int = 1, fields: int = 6):
    return await request.form(max_files=files, max_fields=fields, max_part_size=MAX_UPLOAD)


async def verify_route(request: Request):
    if not auth.allow(client_ip(request), "verify", 60, 3600):
        return error(429, "Too many checks from your network this hour.")
    try:
        form = await _form(request)
    except Exception as e:
        return error(400, "Couldn't read the upload (one image, up to 30 MB).")
    up = form.get("file")
    if not hasattr(up, "read"):
        return error(400, "Send a file as 'file'.")
    data = await up.read()
    if not data or len(data) > MAX_UPLOAD:
        return error(400, "Send an image under 30 MB.")
    try:
        out = await run_in_threadpool(features.verify_file, data, CACHE)
    except Exception as e:
        return error(400, f"Couldn't read that image: {type(e).__name__}")
    out["filename"] = up.filename
    return JSONResponse(out)


async def likeness_route(request: Request):
    if not auth.allow(client_ip(request), "likeness", 30, 3600):
        return error(429, "Too many checks from your network this hour.")
    try:
        form = await _form(request, fields=6)
        fidelity = parse_fidelity(form.get("fidelity", DEFAULT_FIDELITY))
    except Exception as e:
        return error(400, str(e))
    key, up = str(form.get("key", "")), form.get("reference")
    r = _result_or_404(key, fidelity)
    if not r:
        return error(404, "Restore the photo first.")
    if not hasattr(up, "read"):
        return error(400, "Add a reference photo of the same person.")
    try:
        ref = np.asarray(_normalise_image(await up.read()).convert("RGB"))
    except ValueError as e:
        return error(400, str(e))
    folder = CACHE / key
    cands = []
    if r.get("face_original") and (folder / r["face_original"]).exists():
        cands.append(("The damaged scan", np.asarray(Image.open(folder / r["face_original"]).convert("RGB"))))
    for i, f in enumerate(r.get("faces") or [], 1):
        if (folder / f["file"]).exists():
            cands.append((f"Guess {i}", np.asarray(Image.open(folder / f["file"]).convert("RGB"))))
    if not cands:
        return error(409, "This photo has no invented face to check.")
    try:
        with FEATURE_LOCK:
            out = await run_in_threadpool(features.likeness, ref, cands)
    except ValueError as e:
        return error(422, str(e))
    return JSONResponse(out)


async def compare_route(request: Request):
    if not auth.allow(client_ip(request), "compare", 30, 3600):
        return error(429, "Too many comparisons from your network this hour.")
    try:
        form = await _form(request, files=0)
        fidelity = parse_fidelity(form.get("fidelity", DEFAULT_FIDELITY))
    except Exception as e:
        return error(400, str(e))
    key = str(form.get("key", ""))
    r = _result_or_404(key, fidelity)
    if not r:
        return error(404, "Restore the photo first.")
    folder = CACHE / key
    orig = np.asarray(Image.open(folder / r["files"]["original"]).convert("RGB"))
    mfile = r["files"].get("mask")
    if mfile and (folder / mfile).exists():
        dmg = np.asarray(Image.open(folder / mfile).convert("L")) > 127
    else:
        dmg = np.asarray(Image.open(folder / r["files"]["label"]).convert("L")) > 0
    face = None
    if hook.pipeline_name() == "real":
        from pipeline.codeformer import restore_face as face
    out_dir = hook.fidelity_dir(folder, fidelity) / "compare"
    try:
        with FEATURE_LOCK:
            meta = await run_in_threadpool(features.typical_restore, orig, dmg, out_dir, face)
    except Exception as e:
        traceback.print_exc()
        return error(500, f"Comparison failed: {type(e).__name__}: {e}")
    return JSONResponse(meta)


def _color_meta(key: str, fidelity: float):
    f = hook.fidelity_dir(CACHE / key, fidelity) / "color" / "color.json"
    return json.loads(f.read_text()) if f.exists() else None


async def sidecar_route(request: Request):
    key = request.path_params["key"]
    try:
        fidelity = parse_fidelity(request.query_params.get("fidelity", DEFAULT_FIDELITY))
    except ValueError as e:
        return error(400, str(e))
    r = _result_or_404(key, fidelity)
    if not r:
        return error(404, "Restore the photo first.")
    source = json.loads((CACHE / key / "source.json").read_text())
    row = features.catalog_row(key, r, source, _color_meta(key, fidelity))
    stem = Path(source.get("filename", "photo")).stem or "photo"
    if request.query_params.get("format") == "json":
        return JSONResponse(features.sidecar_json(row), headers={"Content-Disposition": f'attachment; filename="{stem}.coldcase.json"'})
    return Response(features.sidecar_xmp(row), media_type="application/rdf+xml",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.xmp"'})


def _batch_file(bid: str) -> Path:
    return BATCHES / f"{bid}.json"


def _csv_safe(v):
    """Spreadsheet apps run cells starting with = + - @ as formulas; a filename must never do that."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


async def batch_create_route(request: Request):
    if queue_full():
        return error(503, "The restorer is very busy right now. Please try again in a few minutes.")
    try:
        form = await request.form(max_files=40, max_fields=50, max_part_size=MAX_UPLOAD)
    except Exception:
        return error(400, "Couldn't read the upload (max 40 files, 30 MB each).")
    n_files = sum(1 for up in form.getlist("files") if hasattr(up, "read"))
    if not auth.allow_n(client_ip(request), "upload", max(1, n_files), 40, 3600):
        return error(429, "That batch would go over 40 photos this hour from your network. Try fewer, or later.")
    kind = "document" if str(form.get("kind", "")).lower() == "document" else "photo"
    items = []
    for up in form.getlist("files"):
        if not hasattr(up, "read"):
            continue
        data = await up.read()
        if not data or len(data) > MAX_UPLOAD:
            items.append({"filename": up.filename, "error": "empty or over 30 MB"})
            continue
        try:
            key = await run_in_threadpool(ingest, data, filename=up.filename or "upload", kind=kind)
        except ValueError as e:
            items.append({"filename": up.filename, "error": str(e)})
            continue
        enqueue(key, DEFAULT_FIDELITY)
        items.append({"filename": up.filename, "key": key, "kind": kind})
    if not any(i.get("key") for i in items):
        return error(400, "None of those files could be read as images.")
    u = current_user(request)
    if u:
        for i in items:
            if i.get("key"):
                auth.add_case(u["id"], i["key"], i["filename"] or "Batch photo", kind)
    bid = uuid.uuid4().hex
    BATCHES.mkdir(parents=True, exist_ok=True)
    _batch_file(bid).write_text(json.dumps({"id": bid, "created": now(), "items": items}))
    return JSONResponse(_batch_status(bid))


def _batch_status(bid: str) -> dict | None:
    f = _batch_file(bid)
    if not (len(bid) == 32 and set(bid) <= KEY_CHARS and f.exists()):
        return None
    b = json.loads(f.read_text())
    rows = []
    for it in b["items"]:
        row = {"filename": it.get("filename"), "key": it.get("key"), "status": "error" if it.get("error") else "queued",
               "error": it.get("error")}
        if it.get("key"):
            r = cached_result(it["key"], DEFAULT_FIDELITY)
            if r:
                row["status"] = "done"
                row["pixel_summary"] = r.get("pixel_summary")
                row["thumb"] = r["files"].get("restored")
            else:
                jid = ACTIVE.get((it["key"], DEFAULT_FIDELITY))
                job = JOBS.get(jid) if jid else None
                if job:
                    row["status"] = job.status
                    row["position"] = queue_position(job)
                    if job.status == "error":
                        row["error"] = job.error
                else:  # not queued (e.g. the server restarted): queue it again
                    enqueue(it["key"], DEFAULT_FIDELITY)
        rows.append(row)
    rows_done = [r for r in rows if r["status"] == "done"]
    rows_sorted = sorted(rows, key=lambda r: -((r.get("pixel_summary") or {}).get("invented") or -1))
    return {"id": bid, "created": b["created"], "total": len(rows), "done": len(rows_done), "items": rows_sorted}


async def batch_route(request: Request):
    st = _batch_status(request.path_params["bid"])
    return JSONResponse(st) if st else error(404, "No such batch.")


async def batch_csv_route(request: Request):
    st = _batch_status(request.path_params["bid"])
    if not st:
        return error(404, "No such batch.")
    buf = io.StringIO()
    w = None
    for it in st["items"]:
        if not it.get("key"):
            continue
        source = json.loads((CACHE / it["key"] / "source.json").read_text())
        row = features.catalog_row(it["key"], cached_result(it["key"], DEFAULT_FIDELITY), source,
                                   _color_meta(it["key"], DEFAULT_FIDELITY))
        row["status"] = it["status"]
        if w is None:
            w = csv.DictWriter(buf, fieldnames=list(row))
            w.writeheader()
        w.writerow({k: _csv_safe(v) for k, v in row.items()})
    return PlainTextResponse(buf.getvalue(), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="coldcase_batch_{st["id"][:8]}.csv"'})


def preload_models() -> None:
    """Load the segmenter, SDXL and CodeFormer once at startup, so the first visitor's
    upload doesn't wait 20-40 s for model loading. Failures are logged, not fatal."""
    t0 = time.time()
    for name, load in (("segmenter", "pipeline.segment:get_model"),
                       ("scratch detector", "pipeline.scratch_ms:get_model"),
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
    Route("/auth/signup", signup_route, methods=["POST"]),
    Route("/auth/login", login_route, methods=["POST"]),
    Route("/auth/logout", logout_route, methods=["POST"]),
    Route("/auth/me", me_route),
    Route("/cases", cases_route, methods=["GET", "POST"]),
    Route("/verify", verify_route, methods=["POST"]),
    Route("/likeness", likeness_route, methods=["POST"]),
    Route("/compare", compare_route, methods=["POST"]),
    Route("/sidecar/{key}", sidecar_route),
    Route("/batch", batch_create_route, methods=["POST"]),
    Route("/batch/{bid}", batch_route),
    Route("/batch/{bid}/csv", batch_csv_route),
    Route("/jobs/{job_id}", job_route),
    Route("/results/{key}", result_route),
    Route("/results/{key}/{artifact:path}", artifact_route),
]
if FRONTEND_DIST.is_dir():  # serve the built site too, so one tunnel URL is enough
    routes.append(Mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="site"))

app = Starlette(
    routes=routes,
    lifespan=lifespan,
    middleware=[
        Middleware(SecurityHeaders),
        Middleware(
            CORSMiddleware,
            # only our site may call the API from a browser (override with CV_ALLOWED_ORIGINS)
            allow_origins=[o.strip() for o in os.environ.get(
                "CV_ALLOWED_ORIGINS",
                "https://cold-case-t1s8.onrender.com,http://localhost:8000,http://127.0.0.1:8000,http://localhost:5173",
            ).split(",")],
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type"],
            max_age=600,
        ),
        Middleware(BodyLimit),   # inside CORS, so even a 413 reaches the browser readably
    ],
)
