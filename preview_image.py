import base64
import json
import sys

import cv2
import numpy as np


def fail(message):
    print(json.dumps({"ok": False, "message": message}))
    raise SystemExit(1)


def main():
    if len(sys.argv) < 2:
        fail("Usage: preview_image.py <image_path>")

    image_path = sys.argv[1]
    img = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)

    if img is None:
        try:
            from PIL import Image
            pil = Image.open(image_path).convert("RGB")
            img = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception as e:
            fail(f"Could not read image: {e}")

    # Normalize 16-bit to 8-bit preserving full dynamic range
    if img.dtype != np.uint8:
        img = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)

    # Ensure 3-channel BGR for JPEG encoding
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        fail("Could not encode image as JPEG")

    data_url = "data:image/jpeg;base64," + base64.b64encode(buf).decode()
    print(json.dumps({"ok": True, "dataUrl": data_url}))


if __name__ == "__main__":
    main()
