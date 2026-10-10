import json, numpy as np
from PIL import Image
from backend.pipeline.codeformer import restore_face

img = np.asarray(Image.open("outputs/face_test_restored.png").convert("RGB"))
x, y, w, h = json.load(open("test_inputs/face_test_faces.json"))[0]
p = int(0.15 * max(w, h))
crop = img[max(0, y - p):y + h + p, max(0, x - p):x + w + p]
c = np.asarray(Image.fromarray(crop).resize((512, 512), Image.LANCZOS))
outs = [restore_face(c, fw) for fw in (1.0, 0.7, 0.3)]
Image.fromarray(np.hstack([c] + outs)).save("outputs/codeformer_smoke.png")
print("saved outputs/codeformer_smoke.png  (input | w=1.0 | w=0.7 | w=0.3)")
