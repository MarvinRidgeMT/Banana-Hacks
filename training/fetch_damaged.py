"""Download genuinely damaged old photos from Wikimedia Commons (for demo photos + real-photo IoU)."""
from pathlib import Path
import concurrent.futures as cf
from tqdm import tqdm
import fetch_photos as fp

fp.OUT = Path("data/real_damaged")
fp.OUT.mkdir(parents=True, exist_ok=True)
fp.QUERIES = [
    "damaged photograph",
    "torn photograph portrait",
    "scratched old photograph",
    "water damaged photograph",
    "damaged tintype portrait",
    "damaged daguerreotype",
    "cracked glass plate negative",
    "faded damaged family photograph",
]
fp.TARGET = 300

if __name__ == "__main__":
    urls = fp.collect()
    with cf.ThreadPoolExecutor(4) as ex:
        list(tqdm(ex.map(fp.get, urls.items()), total=len(urls)))
    print("saved", len(list(fp.OUT.glob("*.jpg"))), "photos to", fp.OUT)
