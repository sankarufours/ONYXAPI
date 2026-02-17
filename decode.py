#!/usr/bin/env python3
"""Decode payload from a circular generator image (adapted from appnew.decode).
"""
import math
import os
import cv2
import numpy as np
try:
    from .utils import bits_to_bytes, crc32_bytes
except Exception:
    from utils import bits_to_bytes, crc32_bytes


def find_yellow_markers(img):
    def detect_with_range(lower, upper):
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        m = cv2.inRange(hsv, lower, upper)
        kernel = np.ones((5, 5), np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        found = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 30:
                continue
            M = cv2.moments(cnt)
            if M["m00"] == 0:
                continue
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
            found.append((cx, cy, area))
        return found
    # try magenta/magento markers first (h around 150 in OpenCV 0-179 scale)
    lower_m = np.array([140, 60, 50])
    upper_m = np.array([170, 255, 255])
    found_m = detect_with_range(lower_m, upper_m)
    if len(found_m) >= 4:
        found_sorted = sorted(found_m, key=lambda t: t[2], reverse=True)[:4]
        return [(cx, cy) for (cx, cy, a) in found_sorted]

    # fall back to yellow ranges
    lower = np.array([18, 80, 120])
    upper = np.array([45, 255, 255])
    found = detect_with_range(lower, upper)
    if len(found) >= 4:
        found_sorted = sorted(found, key=lambda t: t[2], reverse=True)[:4]
        return [(cx, cy) for (cx, cy, a) in found_sorted]
    lower2 = np.array([10, 60, 80])
    upper2 = np.array([50, 255, 255])
    found2 = detect_with_range(lower2, upper2)
    if len(found2) >= 4:
        found_sorted = sorted(found2, key=lambda t: t[2], reverse=True)[:4]
        return [(cx, cy) for (cx, cy, a) in found_sorted]
    if len(found2) > 0:
        return [(cx, cy) for (cx, cy, a) in found2]
    return [(cx, cy) for (cx, cy, a) in found]


def order_markers(centers):
    if len(centers) != 4:
        return None
    cx = sum([c[0] for c in centers]) / 4.0
    cy = sum([c[1] for c in centers]) / 4.0

    def angle(c):
        return math.degrees(math.atan2(c[1] - cy, c[0] - cx)) % 360

    centers_sorted = sorted(centers, key=angle)
    angles = [angle(c) for c in centers_sorted]
    idx0 = min(range(4), key=lambda i: abs(((angles[i] - 45 + 180) % 360) - 180))
    ordered = [centers_sorted[(idx0 + i) % 4] for i in range(4)]
    return ordered


def decode_from_warp(warp, rings=6, sectors=36, debug=False, debug_prefix="debug", thresh=150, color_mode='cyan', patch=6):
    h, w = warp.shape[:2]
    cx = w // 2
    cy = h // 2
    outer_radius = int(w * 0.45)
    inner_radius = int(w * 0.12)
    ring_step = (outer_radius - inner_radius) / max(1, (rings + 1))

    if color_mode == 'gray':
        sample_img = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)
    elif color_mode == 'cyan':
        b, g, r = cv2.split(warp)
        metric = (b.astype('int32') + g.astype('int32') - r.astype('int32')) // 2
        metric = metric.clip(0, 255).astype('uint8')
        sample_img = metric
    else:
        sample_img = cv2.cvtColor(warp, cv2.COLOR_BGR2GRAY)

    patch_rad = int(patch)

    def sample_with_threshold(t, rstep=None):
        bits_local = []
        sample_points_local = []
        patch_size = max(1, patch_rad * 2)
        for r in range(1, rings + 1):
            used_step = ring_step if rstep is None else rstep
            rad = inner_radius + r * used_step
            for s in range(sectors):
                theta = 2 * math.pi * (s / sectors)
                fx = float(cx + rad * math.cos(theta))
                fy = float(cy + rad * math.sin(theta))
                try:
                    patch_img = cv2.getRectSubPix(sample_img, (patch_size, patch_size), (fx, fy))
                except Exception:
                    patch_img = sample_img[max(0, int(fy)-patch_rad):int(fy)+patch_rad, max(0, int(fx)-patch_rad):int(fx)+patch_rad]
                if patch_img is None or patch_img.size == 0:
                    bits_local.append(0)
                    sample_points_local.append((fx, fy, 0))
                    continue
                median = int(np.median(patch_img))
                bit = 1 if median > t else 0
                bits_local.append(bit)
                sample_points_local.append((fx, fy, bit))
        return bits_local, sample_points_local

    bits, sample_points = sample_with_threshold(thresh)

    data = bits_to_bytes(bits)
    if len(data) < 6:
        return None, "too_short"
    length = int.from_bytes(data[0:2], "big")
    if 2 + length + 4 > len(data):
        for t in range(max(30, thresh - 50), min(230, thresh + 51), 5):
            if t == thresh:
                continue
            tbits, tsample_points = sample_with_threshold(t)
            tdata = bits_to_bytes(tbits)
            if len(tdata) < 6:
                continue
            tlength = int.from_bytes(tdata[0:2], "big")
            if 2 + tlength + 4 > len(tdata):
                continue
            tpayload = tdata[2:2+tlength]
            tcrc_read = int.from_bytes(tdata[2+tlength:2+tlength+4], "big")
            tcrc_calc = crc32_bytes(tpayload)
            if tcrc_read == tcrc_calc:
                try:
                    text = tpayload.decode("utf-8")
                except Exception:
                    text = tpayload.hex()
                if debug:
                    try:
                        cv2.imwrite(f"{debug_prefix}_warp.png", warp)
                        overlay = warp.copy()
                        for (x, y, bit) in tsample_points:
                            color = (0, 255, 0) if bit else (0, 0, 255)
                            cv2.circle(overlay, (int(x), int(y)), 6, color, 2)
                        cv2.imwrite(f"{debug_prefix}_samples_autotuned_{t}.png", overlay)
                    except Exception:
                        pass
                return text, None
        if debug:
            try:
                cv2.imwrite(f"{debug_prefix}_warp.png", warp)
            except Exception:
                pass
        return None, f"declared_length_too_large (declared={length} available={len(data)-6})"
    payload = data[2:2+length]
    crc_read = int.from_bytes(data[2+length:2+length+4], "big")
    crc_calc = crc32_bytes(payload)
    if crc_read != crc_calc:
        old_ring_step = (outer_radius - inner_radius) / max(1, rings)
        if abs(old_ring_step - ring_step) > 0.0001:
            obits, osample_points = sample_with_threshold(thresh, rstep=old_ring_step)
            odata = bits_to_bytes(obits)
            if len(odata) >= 6:
                olength = int.from_bytes(odata[0:2], "big")
                if 2 + olength + 4 <= len(odata):
                    opayload = odata[2:2+olength]
                    ocrc_read = int.from_bytes(odata[2+olength:2+olength+4], "big")
                    ocrc_calc = crc32_bytes(opayload)
                    if ocrc_read == ocrc_calc:
                        try:
                            text = opayload.decode("utf-8")
                        except Exception:
                            text = opayload.hex()
                        if debug:
                            try:
                                cv2.imwrite(f"{debug_prefix}_warp_oldspacing.png", warp)
                                overlay = warp.copy()
                                for (x, y, bit) in osample_points:
                                    color = (0, 255, 0) if bit else (0, 0, 255)
                                    cv2.circle(overlay, (int(x), int(y)), 6, color, 2)
                                cv2.imwrite(f"{debug_prefix}_samples_oldspacing.png", overlay)
                            except Exception:
                                pass
                        return text, None
        if debug:
            try:
                cv2.imwrite(f"{debug_prefix}_warp.png", warp)
                overlay = warp.copy()
                for (x, y, bit) in sample_points:
                    color = (0, 255, 0) if bit else (0, 0, 255)
                    cv2.circle(overlay, (int(x), int(y)), 6, color, 2)
                cv2.imwrite(f"{debug_prefix}_samples.png", overlay)
            except Exception:
                pass
        return None, f"crc_mismatch (read={crc_read:08x} calc={crc_calc:08x})"
    try:
        text = payload.decode("utf-8")
    except Exception:
        text = payload.hex()
    return text, None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="infile", required=True)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--patch", type=int, default=6, help="radius (pixels) of sampling patch; default 6")
    parser.add_argument("--thresh", type=int, default=150)
    parser.add_argument("--color-mode", choices=['gray','cyan'], default='cyan')
    parser.add_argument("--rings", type=int, default=6)
    parser.add_argument("--sectors", type=int, default=36)
    args = parser.parse_args()
    img = cv2.imread(args.infile)
    if img is None:
        print("Unable to open", args.infile)
        return
    centers = find_yellow_markers(img)
    # filter out any detected yellow-like blobs near the image center (possible center marker)
    h_img, w_img = img.shape[:2]
    cx_img = w_img // 2
    cy_img = h_img // 2
    outer_radius_img = int(min(w_img, h_img) * 0.45)
    min_dist_sq = (outer_radius_img * 0.6) ** 2
    filtered = [c for c in centers if (c[0] - cx_img) ** 2 + (c[1] - cy_img) ** 2 >= min_dist_sq]
    if len(filtered) >= 4:
        centers = filtered
    if len(centers) < 4:
        print("Found markers:", centers)
        print("Need 4 yellow markers for reliable decode")
        return
    ordered = order_markers(centers)
    if ordered is None:
        print("Unable to order markers")
        return

    # canonical square (markers placed outside outermost data ring)
    W = 1300
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
        x = cx + int((circle_rad - int(W*0.015)*1.3) * math.cos(a))
        y = cy + int((circle_rad - int(W*0.015)*1.3) * math.sin(a))
        canon.append((x, y))

    src = np.array(ordered, dtype=np.float32)
    dst = np.array(canon, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    warp = cv2.warpPerspective(img, M, (W, W))

    text, err = decode_from_warp(warp, rings=args.rings, sectors=args.sectors, debug=args.debug, debug_prefix=os.path.splitext(os.path.basename(args.infile))[0] + "_debug", thresh=args.thresh, color_mode=args.color_mode, patch=args.patch)
    if err:
        print("Decode error:", err)
        if args.debug:
            try:
                b, g, r = cv2.split(warp)
                dbg_metric = (b.astype('int32') + g.astype('int32') - r.astype('int32')) // 2
                gray = dbg_metric.clip(0, 255).astype('uint8')
                bits = []
                cx = W // 2
                cy = W // 2
                outer_radius = int(W * 0.45)
                inner_radius = int(W * 0.12)
                ring_step = (outer_radius - inner_radius) / max(1, (args.rings + 1))
                for r in range(1, args.rings + 1):
                    rad = inner_radius + r * ring_step
                    for s in range(args.sectors):
                        theta = 2 * math.pi * (s / args.sectors)
                        fx = float(cx + rad * math.cos(theta))
                        fy = float(cy + rad * math.sin(theta))
                        p = int(getattr(args, 'patch', 6))
                        patch_size = max(1, p * 2)
                        try:
                            patch = cv2.getRectSubPix(gray, (patch_size, patch_size), (fx, fy))
                        except Exception:
                            patch = gray[max(0, int(fy)-p):int(fy)+p, max(0, int(fx)-p):int(fx)+p]
                        median = int(np.median(patch)) if patch is not None and patch.size else 0
                        bits.append(1 if median > 150 else 0)
                raw = bits_to_bytes(bits)
                if len(raw) >= 6:
                    header = raw[0:2]
                    length = int.from_bytes(header, "big")
                    payload = raw[2:2+length] if 2+length <= len(raw) else raw[2:]
                    crc_read = raw[2+length:2+length+4] if 2+length+4 <= len(raw) else b""
                    crc_calc = crc32_bytes(payload) if payload else 0
                    print("Header:", header.hex(), "declared_length:", length)
                    print("Payload (hex, first 100 chars):", payload.hex()[:200])
                    print("CRC read:", crc_read.hex(), "CRC calc:", f"{crc_calc:08x}")
            except Exception:
                pass
    else:
        print(text)


if __name__ == "__main__":
    main()
