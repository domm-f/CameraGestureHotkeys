from pathlib import Path
from urllib.request import Request, urlopen

URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
DEST = Path(__file__).resolve().parent / "pose_landmarker_lite.task"

if DEST.exists() and DEST.stat().st_size > 1_000_000:
    print(f"Model already exists: {DEST.name}")
    raise SystemExit(0)

print("Downloading the official MediaPipe pose model...")
request = Request(URL, headers={"User-Agent": "CameraGestureHotkeys"})
with urlopen(request, timeout=120) as response, DEST.open("wb") as output:
    total = int(response.headers.get("Content-Length", "0"))
    downloaded = 0
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        output.write(chunk)
        downloaded += len(chunk)
        if total:
            print(f"  {downloaded * 100 // total}%", end="\r")
print(f"\nSaved {DEST.name} ({DEST.stat().st_size / 1024 / 1024:.1f} MB)")
