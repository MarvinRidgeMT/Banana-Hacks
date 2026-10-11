# Cold Case website and API

Person B's half: the web API in `backend/` and the website in `frontend/`.
Person A's pipeline (`backend/pipeline/`) is untouched; the API calls
`pipeline.restore.restore(path, fidelity=w)` through `backend/restore_hook.py`.

## What goes where

```
backend/
  api.py               web API: upload, job queue, cache, files
  restore_hook.py      the only file that knows restore()'s output format
  precompute_demos.py  run at code freeze: every demo × every fidelity
  metrics.json         the numbers shown on the site (IoU etc.) — edit freely
  demos/               demo photos + demos.json (titles, credits, licenses)
  dev/stub_pipeline.py FAKE restore() for UI work without the models
  tests/smoke_test.py  end-to-end check of every route
  requirements-web.txt
frontend/              React + Vite + TypeScript + Tailwind
cache/                 created on first run; results live here (don't commit)
```

## Run it on the Mac (two terminals)

```bash
# 1. API (from backend/, so `pipeline` imports work)
cd backend
pip install -r requirements-web.txt
uvicorn api:app --host 0.0.0.0 --port 8000

# 2. Website, with live reload
cd frontend
npm install
npm run dev          # opens http://localhost:5173, API calls go to :8000
```

No models handy, or working on the UI only? Start the API with the fake
pipeline instead. The site shows a yellow "Test mode" bar so nobody mistakes
its output for real results:

```bash
CV_PIPELINE=stub uvicorn api:app --port 8000
```

Check everything works (in a third terminal, API running):

```bash
cd backend
python tests/smoke_test.py http://localhost:8000 demos/hero.png demos/hero_mask.png
```

It ends with `ALL CHECKS PASSED`, or names the first thing that broke.

## Demo photos

1. Put each photo in `backend/demos/` with the file name used in `demos.json`
   (`hero.png`, `inferred.png`, `light.png`, `backup.png`).
2. Next to it, the hand-painted mask `<name>_mask.png` (white = content lost,
   same size as the photo) and Person A's `<name>_faces.json` if there is one.
3. Fill in `credit`, `source_url` and `license` in `demos.json`. The cards show
   them, and judges will ask.
4. Restart the API. It queues every demo at w = 0.7 first, then 0.3 and 1.0.

At code freeze, compute everything up front instead:

```bash
cd backend && python precompute_demos.py      # add --force to redo
```

A demo with a mask file is recorded as "Damage marked by a person" in the
manifest (`human_edited_mask: true`), because it was.

## Putting it online

The backend runs on the Mac; judges reach it through a Cloudflare Tunnel.

**Simplest: one URL for everything.** The API also serves the built site.

```bash
cd frontend && npm run build                  # creates frontend/dist
cd ../backend && uvicorn api:app --port 8000  # now serves the site at /
cloudflared tunnel --url http://localhost:8000
```

Share the `https://….trycloudflare.com` address it prints.

**Or: site on Vercel, API through the tunnel.**
- Vercel project: root directory `frontend`, build `npm run build`, output `dist`.
- Environment variable `VITE_API_URL` = the tunnel address (no trailing slash).
- A quick tunnel's address changes every time `cloudflared` restarts; update
  `VITE_API_URL` and redeploy when it does, or use a named tunnel for a fixed address.
- Optional: `CV_ALLOWED_ORIGINS=https://your-site.vercel.app` on the API
  to accept only your site (default accepts any).

Either way: **the Mac must be awake** with the API and tunnel running whenever
a judge might open the link. Turn off sleep (System Settings → Battery →
prevent automatic sleeping on power adapter) and keep it plugged in.

## Settings (environment variables)

| Variable | Default | Use |
|---|---|---|
| `CV_PIPELINE` | real | `stub` = fake results for UI work |
| `CV_CACHE` | `../cache` | where results are stored |
| `CV_DEMOS` | `backend/demos` | demo photo folder |
| `CV_WARM_DEMOS` | `1` | `0` = don't queue demos at startup |
| `CV_LABELS` | `0,1,2` | label values for observed, inferred, invented |
| `CV_BBOX` | detected | force region boxes to `xyxy` or `xywh` |
| `CV_ALLOWED_ORIGINS` | `*` | comma-separated sites allowed to call the API |
| `CV_SITE` | `frontend/dist` | built site to serve |

## API

| Route | Does |
|---|---|
| `GET /health` | pipeline mode, queue length |
| `GET /metrics` | contents of `metrics.json` |
| `GET /demos` | demo photos with their cache keys |
| `POST /restore` | form: `file` (or `key`), optional `mask`, `fidelity` (default 0.7), `all_fidelities` (default true) → job |
| `GET /jobs/{id}` | job status; includes the result when done |
| `GET /results/{key}?fidelity=w` | result JSON (200), or 202 if that step isn't computed yet |
| `GET /results/{key}/{file}` | any result file; add `?download=1` to save it |

One photo is restored at a time; repeats of the same photo, mask and
fidelity come straight from the cache.

## How the site reads the map

For each result the API writes `regions.png`: red + green = region id,
blue = class (0 observed, 1 inferred, 2 invented). The page draws the
overlay from it and reads it under the cursor for the tooltip, so the
colours, the hover and the legend all come from the same pixels. The legend
percentages are computed from the label map itself; if the pipeline's
`pixel_summary` disagrees by more than 1 point, a note appears under
"Pipeline notes" on the page.
