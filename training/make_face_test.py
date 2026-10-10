import sys, cv2, numpy as np
from pathlib import Path
from damage_synth import scratches, dust, age, _fill_paper

YUNET = "weights/face_detection_yunet_2023mar.onnx"
best = None
for f in sorted(Path("samples").glob("*.jpg")):
    img = cv2.imread(str(f))
    h, w = img.shape[:2]
    s = 1024 / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    det = cv2.FaceDetectorYN.create(YUNET, "", (w, h), 0.6, 0.3, 50)
    _, faces = det.detect(img)
    if faces is None:
        continue
    for fc in faces:
        if best is None or fc[2] > best[2][2]:
            best = (f, img, fc)
if best is None:
    sys.exit("No faces found in samples/. Add a portrait photo to samples/ and try again.")

f, img, fc = best
x, y, fw, fh = fc[:4]
rng = np.random.default_rng(int(sys.argv[1]) if len(sys.argv) > 1 else 3)
xf = img.astype(np.float32)
mask = np.zeros(img.shape[:2], np.uint8)
# a ragged hole through the middle of the face (eye, cheek, mouth)
cx, cy = x + fw * rng.uniform(.35, .65), y + fh * rng.uniform(.4, .6)
r = 0.33 * max(fw, fh)
ang = np.sort(rng.uniform(0, 2 * np.pi, 18))
rad = r * rng.uniform(0.6, 1.3, 18)
poly = np.stack([cx + rad * np.cos(ang), cy + rad * np.sin(ang)], 1).astype(np.int32)
m = np.zeros(img.shape[:2], np.uint8)
cv2.fillPoly(m, [poly], 1)
_fill_paper(xf, m, rng)
mask |= m
scratches(xf, mask, rng)
dust(xf, mask, rng)
age(xf, rng)
Path("test_inputs").mkdir(exist_ok=True)
cv2.imwrite("test_inputs/face_test.png", np.clip(xf, 0, 255).astype(np.uint8))
cv2.imwrite("test_inputs/face_test_mask.png", mask * 255)
print(f"used {f.name}: face is {int(fw)}x{int(fh)} px")
import json
json.dump([[int(x), int(y), int(fw), int(fh)]], open("test_inputs/face_test_faces.json", "w"))
print("wrote test_inputs/face_test_faces.json")
