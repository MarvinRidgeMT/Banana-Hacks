import time, requests, concurrent.futures as cf
from pathlib import Path
from tqdm import tqdm

OUT = Path("data/clean"); OUT.mkdir(parents=True, exist_ok=True)
API = "https://commons.wikimedia.org/w/api.php"
HEAD = {"User-Agent": "ChronoVisage/0.1 (Banana Hacks 2026 student project; siddharth.tumati@gmail.com)"}
QUERIES = [
    "black and white portrait photograph 1900s",
    "studio portrait photograph 1910s",
    "vintage family photograph",
    "black and white street photograph 1920s",
    "historical group portrait photograph",
    "black and white photograph building 1900",
]
TARGET = 3000

def search(q, offset):
    p = {"action": "query", "format": "json", "generator": "search",
         "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6, "gsrlimit": 50,
         "gsroffset": offset, "prop": "imageinfo",
         "iiprop": "url|size|mime", "iiurlwidth": 1024}
    r = requests.get(API, params=p, headers=HEAD, timeout=30); r.raise_for_status()
    j = r.json()
    return list(j.get("query", {}).get("pages", {}).values()), j.get("continue", {}).get("gsroffset")

def collect():
    urls = {}
    for q in QUERIES:
        off = 0
        while off is not None and off < 1000 and len(urls) < TARGET:
            pages, off = search(q, off)
            for pg in pages:
                ii = (pg.get("imageinfo") or [{}])[0]
                if ii.get("mime") != "image/jpeg" or ii.get("width", 0) < 600:
                    continue
                urls[pg["pageid"]] = ii.get("thumburl") or ii["url"]
            time.sleep(0.5)
        print(f"{q}: {len(urls)} total")
    return urls

def get(item):
    pid, url = item
    f = OUT / f"{pid}.jpg"
    if f.exists():
        return
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEAD, timeout=30)
            if r.status_code == 200:
                f.write_bytes(r.content); return
            time.sleep(5 if r.status_code == 429 else 1)
        except requests.RequestException:
            time.sleep(2)

if __name__ == "__main__":
    urls = collect()
    with cf.ThreadPoolExecutor(4) as ex:
        list(tqdm(ex.map(get, urls.items()), total=len(urls)))
    print("saved", len(list(OUT.glob("*.jpg"))), "photos")