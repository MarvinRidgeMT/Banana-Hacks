"""Paint damage masks by hand (white = content lost). Saves <name>_mask.png next to each photo.
Usage: python training/paint_mask.py demo/*.png
  drag        paint (or erase, in erase mode)      e  toggle paint / erase
  [  ]        smaller / bigger brush               z  undo
  f           face mode: drag a box around a face (saves <name>_faces.json)
  s           save and go to next photo            n  skip      q  quit"""
import sys, json, cv2, numpy as np
from pathlib import Path

files = [Path(p) for p in sys.argv[1:] if not p.endswith(("_mask.png", "_damage.png"))]
WIN = "paint damage"
cv2.namedWindow(WIN, cv2.WINDOW_AUTOSIZE)

for f in files:
    img = cv2.imread(str(f))
    if img is None:
        continue
    h, w = img.shape[:2]
    scale = min(1000 / max(h, w), 4.0)          # small photos get enlarged so you can paint precisely
    W, H = round(w * scale), round(h * scale)
    disp = cv2.resize(img, (W, H), interpolation=cv2.INTER_CUBIC)
    mp = f.with_name(f.stem + "_mask.png")
    mask = np.zeros((H, W), np.uint8)
    if mp.exists():
        mask = cv2.resize(cv2.imread(str(mp), 0), (W, H), interpolation=cv2.INTER_NEAREST)
    fp = f.with_name(f.stem + "_faces.json")
    faces = [[v * scale for v in b] for b in json.loads(fp.read_text())] if fp.exists() else []
    st = {"r": 6, "val": None, "pt": None, "cur": (0, 0), "erase": False, "face": False, "box0": None}
    hist = []

    def on_mouse(ev, x, y, flags, _):
        st["cur"] = (x, y)
        if ev == cv2.EVENT_LBUTTONDOWN:
            if st["face"]:
                st["box0"] = (x, y)
                return
            hist.append(mask.copy())
            st["val"] = 0 if st["erase"] else 255
            st["pt"] = (x, y)
            cv2.circle(mask, (x, y), st["r"], st["val"], -1)
        elif ev == cv2.EVENT_MOUSEMOVE and st["val"] is not None:
            cv2.line(mask, st["pt"], (x, y), st["val"], st["r"] * 2)
            st["pt"] = (x, y)
        elif ev == cv2.EVENT_LBUTTONUP:
            if st["face"] and st["box0"]:
                x0, y0 = st["box0"]
                faces.append([min(x0, x), min(y0, y), abs(x - x0), abs(y - y0)])
                st["box0"] = None
            st["val"] = None

    cv2.setMouseCallback(WIN, on_mouse)
    action = None
    while action is None:
        view = disp.copy()
        m = mask > 0
        view[m] = (view[m] * 0.45 + np.array([40, 40, 230]) * 0.55).astype(np.uint8)
        for b in faces:
            x, y, bw, bh = map(int, b)
            cv2.rectangle(view, (x, y), (x + bw, y + bh), (0, 220, 0), 2)
        if st["face"] and st["box0"]:
            cv2.rectangle(view, st["box0"], st["cur"], (0, 220, 0), 1)
        elif not st["face"]:
            cv2.circle(view, st["cur"], st["r"], (255, 255, 255), 1)
        mode = "FACE BOX" if st["face"] else ("ERASE" if st["erase"] else "PAINT")
        cv2.putText(view, f"{f.name}  {mode}  brush {st['r']}  |  s save  n skip  z undo  e erase  f face  [ ] size  q quit",
                    (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
        cv2.putText(view, f"{f.name}  {mode}  brush {st['r']}  |  s save  n skip  z undo  e erase  f face  [ ] size  q quit",
                    (8, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imshow(WIN, view)
        k = cv2.waitKey(15) & 0xFF
        if k == ord("["): st["r"] = max(1, st["r"] - 1)
        elif k == ord("]"): st["r"] = min(80, st["r"] + 2)
        elif k == ord("e"): st["erase"] = not st["erase"]; st["face"] = False
        elif k == ord("f"): st["face"] = not st["face"]
        elif k == ord("z") and st["face"] and faces: faces.pop()
        elif k == ord("z") and st["face"] and faces: faces.pop()
        elif k == ord("z") and st["face"] and faces: faces.pop()
        elif k == ord("z") and hist: mask[:] = hist.pop()
        elif k in (ord("s"), ord("n"), ord("q")): action = chr(k)

    if action == "s":
        full = cv2.resize(mask, (w, h), interpolation=cv2.INTER_NEAREST)
        cv2.imwrite(str(mp), np.where(full > 127, 255, 0).astype(np.uint8))
        print(f"saved {mp}  ({(full > 127).mean():.1%} of photo marked as damage)")
        marker = f.with_name(f.stem + "_unchecked")
        if marker.exists():
            marker.unlink()                       # a person has now checked this mask
        if faces:
            fp.write_text(json.dumps([[round(v / scale) for v in b] for b in faces]))
            print(f"saved {fp}  ({len(faces)} face box)")
    if action == "q":
        break

cv2.destroyAllWindows()
cv2.waitKey(1)
