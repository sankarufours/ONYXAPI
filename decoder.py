import base64
import math
from typing import Optional

import cv2
import numpy as np

try:
    from . import decode as app_decode
except Exception:
    import decode as app_decode


def decode_base64_image(b64str: str, color_mode: str = 'cyan', thresh: int = 100, patch: int = 6, rings: int = 14, sectors: int = 40, size: int = 1300):
    if b64str.startswith('data:'):
        b64str = b64str.split(',', 1)[1]
    try:
        b = base64.b64decode(b64str)
    except Exception:
        return None, 'invalid_base64'
    arr = np.frombuffer(b, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return None, 'invalid_image'

    try:
        centers = app_decode.find_yellow_markers(img)
        h_img, w_img = img.shape[:2]
        cx_img = w_img // 2
        cy_img = h_img // 2
        outer_radius_img = int(min(w_img, h_img) * 0.45)
        min_dist_sq = (outer_radius_img * 0.6) ** 2
        filtered = [c for c in centers if (c[0] - cx_img) ** 2 + (c[1] - cy_img) ** 2 >= min_dist_sq]
        if len(filtered) >= 4:
            centers = filtered
        if len(centers) < 4:
            return None, 'need_4_markers'
        ordered = app_decode.order_markers(centers)
        if ordered is None:
            return None, 'order_failed'

        W = int(size)
        cx = cy = W // 2
        rad = int(W * 0.45)
        marker_r = int(W * 0.015)
        desired_margin = int(W * 0.05)
        max_allowed_margin = max(0, (W // 2) - rad - marker_r - 2)
        marker_margin = min(desired_margin, max_allowed_margin)
        circle_rad = rad + marker_margin + marker_r
        canon = []
        for angle_deg in (45, 135, 225, 315):
            a = math.radians(angle_deg)
            x = cx + int((circle_rad - int(W * 0.015) * 1.3) * math.cos(a))
            y = cy + int((circle_rad - int(W * 0.015) * 1.3) * math.sin(a))
            canon.append((x, y))

        src = np.array(ordered, dtype=np.float32)
        dst = np.array(canon, dtype=np.float32)
        M = cv2.getPerspectiveTransform(src, dst)
        warp = cv2.warpPerspective(img, M, (W, W))

        text, err = app_decode.decode_from_warp(warp, rings=rings, sectors=sectors, debug=False, debug_prefix='api_debug', thresh=thresh, color_mode=color_mode, patch=patch)
        if err:
            return None, err
        return text, None
    except Exception as e:
        return None, f'decode_exception: {e}'
