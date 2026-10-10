import cv2, numpy as np, random, torch
from pathlib import Path
from torch.utils.data import Dataset
from damage_synth import damage

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)

def split_files(root="data/clean", val_frac=0.1, seed=0):
    """90/10 split by photo (not by crop), so validation IoU is honest."""
    files = sorted(Path(root).glob("*.jpg"))
    random.Random(seed).shuffle(files)
    n = int(len(files) * val_frac)
    return files[n:], files[:n]

class DamageDataset(Dataset):
    def __init__(self, files, size=512, train=True):
        self.files, self.size, self.train = list(files), size, train

    def __len__(self):
        return len(self.files)

    def __getitem__(self, i):
        img = cv2.imread(str(self.files[i]))
        if img is None:
            return self[(i + 1) % len(self)]
        # Training: fresh random damage every epoch. Validation: fixed damage per photo.
        rng = np.random.default_rng() if self.train else np.random.default_rng(i)
        h, w = img.shape[:2]
        s = self.size / min(h, w)
        if s > 1 or not self.train:
            img = cv2.resize(img, (max(self.size, round(w * s)), max(self.size, round(h * s))),
                             interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        h, w = img.shape[:2]
        if self.train:
            y, x = rng.integers(0, h - self.size + 1), rng.integers(0, w - self.size + 1)
        else:
            y, x = (h - self.size) // 2, (w - self.size) // 2
        img = np.ascontiguousarray(img[y:y + self.size, x:x + self.size])
        if self.train and rng.random() < 0.5:
            img = np.ascontiguousarray(img[:, ::-1])
        dmg, mask = damage(img, rng)
        rgb = cv2.cvtColor(dmg, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        x = (rgb - MEAN) / STD
        return torch.from_numpy(x.transpose(2, 0, 1)), torch.from_numpy(mask[None].astype(np.float32))