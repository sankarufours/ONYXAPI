#!/usr/bin/env python3
"""Generator adapted from appnew.generate (creates PNG polar payload images).
"""
import argparse
import math
import os
from typing import Optional
from PIL import Image, ImageDraw, ImageFilter
try:
    from .utils import bytes_to_bits, crc32_bytes
except Exception:
    from utils import bytes_to_bits, crc32_bytes


def make_image(payload: bytes, out_path: str, rings=6, sectors=36, size=1300, quality=95, connect_dots=False, connect_style='mesh', connect_thickness=2, connect_color=(0,200,255), bg_color=None, transparent=None, hide_ring=False, bank: Optional[str]=None):
    header = len(payload).to_bytes(2, "big")
    crc = crc32_bytes(payload).to_bytes(4, "big")
    data = header + payload + crc
    bits = bytes_to_bits(data)

    total_bits = rings * sectors
    if len(bits) > total_bits:
        total_bytes = total_bits // 8
        max_payload = max(0, total_bytes - 6)
        raise ValueError(f"Payload too large for {rings}x{sectors} polar grid: need {len(bits)} bits ({len(data)} bytes) but grid holds {total_bits} bits ({total_bytes} bytes). Max payload bytes: {max_payload}.")

    def _parse_color(colstr):
        if colstr is None:
            return None
        if isinstance(colstr, tuple) and len(colstr) == 3:
            return tuple(int(x) for x in colstr)
        s = str(colstr).lstrip('#').lower()
        if s == 'black':
            return (0, 0, 0)
        if len(s) == 3:
            s = ''.join([c*2 for c in s])
        if len(s) != 6:
            return None
        try:
            return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            return None

    default_bg = (9, 14, 20)
    default_vignette = (12, 18, 28)

    parsed_bg = _parse_color(bg_color)
    percent_opacity = None
    if transparent is not None:
        try:
            percent_opacity = int(transparent)
        except Exception:
            try:
                percent_opacity = int(float(transparent))
            except Exception:
                percent_opacity = 0
        percent_opacity = max(0, min(100, percent_opacity))

    if percent_opacity is not None and percent_opacity == 0:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        base_bg = None
    else:
        if parsed_bg is None:
            base_bg = default_bg
        else:
            base_bg = parsed_bg
        if percent_opacity is None:
            img = Image.new("RGB", (size, size), base_bg)
            draw = ImageDraw.Draw(img)
        else:
            alpha = int(255 * (percent_opacity / 100.0))
            img = Image.new("RGBA", (size, size), (base_bg[0], base_bg[1], base_bg[2], alpha))
            draw = ImageDraw.Draw(img)

    cx = cy = size // 2
    outer_radius = int(size * 0.45)

    if not (percent_opacity is not None and percent_opacity == 0):
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.ellipse((cx - outer_radius - 30, cy - outer_radius - 30, cx + outer_radius + 30, cy + outer_radius + 30), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(80))
        if parsed_bg is None:
            vignette_color = default_vignette
        else:
            vignette_color = tuple(min(255, int(c * 1.15) + 3) for c in base_bg)
        if img.mode == "RGBA":
            if percent_opacity is None:
                alpha_val = 255
            else:
                alpha_val = int(255 * (percent_opacity / 100.0))
            vc = (vignette_color[0], vignette_color[1], vignette_color[2], alpha_val)
            img.paste(vc, mask)
        else:
            img.paste(vignette_color, mask)

    marker_r = int(size * 0.015)
    # magento marker colors (outer, inner)
    marker_outer_color = (200, 40, 180)
    marker_inner_color = (120, 20, 80)
    desired_margin = int(size * 0.05)
    max_allowed_margin = max(0, (size // 2) - outer_radius - marker_r - 2)
    marker_margin = min(desired_margin, max_allowed_margin)
    circle_radius = outer_radius + marker_margin + marker_r

    for angle_deg in (45, 135, 225, 315):
        a = math.radians(angle_deg)
        x = cx + int((circle_radius - marker_r * 1.3) * math.cos(a))
        y = cy + int((circle_radius - marker_r * 1.3) * math.sin(a))
        draw.ellipse((x - marker_r, y - marker_r, x + marker_r, y + marker_r), fill=marker_outer_color)
        draw.ellipse((x - marker_r // 2, y - marker_r // 2, x + marker_r // 2, y + marker_r // 2), fill=marker_inner_color)

    inner_radius = int(size * 0.12)
    ring_step = (outer_radius - inner_radius) / max(1, (rings + 1))
    dot_r = max(3, size // 140)

    # center placeholder (original used logo)
    try:
        bank_name = (bank or "").strip().lower() if bank is not None else ""
        if bank_name == 'hsbc':
            logo_file = 'HSBC.png'
        elif bank_name == 'kenanga':
            logo_file = 'Kenanga.png'
        elif bank_name == 'maybank':
            logo_file = 'maybank.png'
        elif bank_name == 'onyx':
            logo_file = 'ONYX.png'
        else:
            # empty or unknown bank -> fall back to drawn magento star
            raise FileNotFoundError('no bank logo requested')

        logo_path = os.path.join(os.path.dirname(__file__), logo_file)
        if not os.path.exists(logo_path):
            raise FileNotFoundError(f'logo not found: {logo_path}')
        logo = Image.open(logo_path)
        logo = logo.convert("RGBA")
        max_diam = max(1, int(inner_radius))
        lw, lh = logo.size
        scale = max_diam / max(lw, lh)
        new_size = (max(1, int(lw * scale)), max(1, int(lh * scale)))
        logo = logo.resize(new_size, Image.LANCZOS)
        lx = cx - new_size[0] // 2
        ly = cy - new_size[1] // 2
        if img.mode == "RGBA":
            img.paste(logo, (lx, ly), logo)
        else:
            tmp = Image.new("RGBA", img.size)
            tmp.paste(logo, (lx, ly), logo)
            img = Image.alpha_composite(img.convert("RGBA"), tmp).convert("RGB")
            draw = ImageDraw.Draw(img)
    except Exception:
        star_outer_r = int(inner_radius * 0.5)
        star_inner_r = max(2, int(star_outer_r * 0.45))
        star_points = []
        spikes = 5
        for i in range(spikes * 2):
            angle = math.pi / spikes * i
            r = star_outer_r if i % 2 == 0 else star_inner_r
            x = cx + int(r * math.cos(angle))
            y = cy + int(r * math.sin(angle))
            star_points.append((x, y))
        star_outer_color = (200, 40, 180)
        star_inner_color = (120, 20, 80)
        draw.polygon(star_points, fill=star_outer_color)
        core_r = max(1, star_inner_r // 2)
        draw.ellipse((cx - core_r, cy - core_r, cx + core_r, cy + core_r), fill=star_inner_color)

    bit_idx = 0
    positions = [[None for _ in range(sectors)] for _ in range(rings)]
    for ri in range(1, rings + 1):
        rad = inner_radius + ri * ring_step
        for s in range(sectors):
            theta = 2 * math.pi * (s / sectors)
            x = cx + rad * math.cos(theta)
            y = cy + rad * math.sin(theta)
            bit = 0
            if bit_idx < len(bits) and bits[bit_idx]:
                bit = 1
                draw.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=(0, 200, 255))
            positions[ri-1][s] = (x, y, bit)
            bit_idx += 1

    if connect_dots:
        thickness = max(1, int(connect_thickness))
        color = connect_color if isinstance(connect_color, tuple) else connect_color

        def draw_ring_connections():
            for ri in range(rings):
                pts = []
                run = []
                for s in range(sectors):
                    x, y, bit = positions[ri][s]
                    if bit:
                        run.append((int(x), int(y)))
                    else:
                        if len(run) >= 2:
                            draw.line(run, fill=color, width=thickness)
                        run = []
                if len(run) >= 2:
                    draw.line(run, fill=color, width=thickness)
                if connect_style == 'smooth':
                    all_pts = [(int(positions[ri][s][0]), int(positions[ri][s][1])) for s in range(sectors) if positions[ri][s][2]]
                    if len(all_pts) >= 2:
                        draw.line(all_pts, fill=color, width=thickness)

        def draw_pattern_connections():
            pts = []
            for ri in range(rings):
                for s in range(sectors):
                    x, y, bit = positions[ri][s]
                    if bit:
                        pts.append((float(x), float(y)))
            if len(pts) < 2:
                return
            unvisited = pts[:]
            path = [unvisited.pop(0)]
            while unvisited:
                last = path[-1]
                idx, dist = min(enumerate(unvisited), key=lambda iv: ((iv[1][0]-last[0])**2 + (iv[1][1]-last[1])**2 ))
                path.append(unvisited.pop(idx))

            def catmull_rom_chain(P, n_points=200):
                if len(P) < 2:
                    return P
                pts = [P[0]] + P + [P[-1]]
                out = []
                for i in range(len(pts)-3):
                    p0 = pts[i]
                    p1 = pts[i+1]
                    p2 = pts[i+2]
                    p3 = pts[i+3]
                    for t_i in range(n_points//(len(pts)-3)):
                        t = t_i / max(1, (n_points//(len(pts)-3)))
                        t2 = t*t
                        t3 = t2*t
                        x = 0.5 * ((2*p1[0]) + (-p0[0]+p2[0])*t + (2*p0[0]-5*p1[0]+4*p2[0]-p3[0])*t2 + (-p0[0]+3*p1[0]-3*p2[0]+p3[0])*t3)
                        y = 0.5 * ((2*p1[1]) + (-p0[1]+p2[1])*t + (2*p0[1]-5*p1[1]+4*p2[1]-p3[1])*t2 + (-p0[1]+3*p1[1]-3*p2[1]+p3[1])*t3)
                        out.append((int(x), int(y)))
                out.append((int(P[-1][0]), int(P[-1][1])))
                return out

            smooth_pts = catmull_rom_chain(path, n_points=max(80, len(path)*20))
            if len(smooth_pts) >= 2:
                draw.line(smooth_pts, fill=color, width=thickness, joint=None)

        def draw_radial_connections():
            for ri in range(rings - 1):
                for s in range(sectors):
                    x, y, bit = positions[ri][s]
                    rx, ry, rbit = positions[ri + 1][s]
                    if bit and rbit:
                        draw.line([(int(x), int(y)), (int(rx), int(ry))], fill=color, width=thickness)

        if connect_style == 'ring':
            draw_ring_connections()
        elif connect_style == 'radial':
            draw_radial_connections()
        elif connect_style == 'mesh':
            draw_ring_connections()
            draw_radial_connections()
        elif connect_style == 'smooth':
            draw_ring_connections()
            draw_radial_connections()
        elif connect_style == 'pattern':
            draw_pattern_connections()
        else:
            draw_ring_connections()
            draw_radial_connections()

    fmt = "PNG"
    if percent_opacity is not None:
        rgba = img.convert("RGBA")
        if percent_opacity >= 100:
            img = rgba
        elif percent_opacity <= 0:
            r, g, b, a = rgba.split()
            new_a = Image.new('L', a.size, 0)
            img = Image.merge('RGBA', (r, g, b, new_a))
        else:
            r, g, b, a = rgba.split()
            factor = percent_opacity / 100.0
            new_a = a.point(lambda v: int(v * factor))
            img = Image.merge('RGBA', (r, g, b, new_a))

    if out_path.lower().endswith((".jpg", ".jpeg")):
        fmt = "JPEG"
        img = img.convert("RGB")
        img.save(out_path, fmt, quality=quality)
    else:
        img.save(out_path, fmt)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True)
    parser.add_argument("--out", default="out.png")
    parser.add_argument("--size", type=int, default=1300, help="output image size (px)")
    parser.add_argument("--hide-ring", action="store_true", help="hide the outer circle ring")
    parser.add_argument("--rings", type=int, default=6)
    parser.add_argument("--sectors", type=int, default=36)
    parser.add_argument("--truncate", action="store_true")
    parser.add_argument("--quality", type=int, default=95)
    parser.add_argument("--connect-dots", action="store_true", help="draw lines connecting neighboring set cyan dots")
    parser.add_argument("--connect-style", choices=["ring","radial","mesh","smooth","pattern"], default="mesh", help="connection style: ring, radial, mesh (both), smooth, or pattern")
    parser.add_argument("--connect-thickness", type=int, default=2, help="thickness of connecting lines")
    parser.add_argument("--connect-color", default="#00C8FF", help="hex color for connecting lines")
    parser.add_argument("--transparent", nargs='?', const='0', default=None, help="make PNG background transparent; optional percentage 0-100 (e.g. --transparent 50). If provided without value, treated as 0 (fully transparent).")
    parser.add_argument("--bank", default='', help="bank name for center logo (HSBC, Kenanga, maybank)")
    args = parser.parse_args()
    payload_bytes = args.payload.encode("utf-8")
    total_bits = args.rings * args.sectors
    total_bytes = total_bits // 8
    max_payload = max(0, total_bytes - 6)
    if len(payload_bytes) > max_payload:
        if args.truncate:
            print(f"Warning: payload too large for {args.rings}x{args.sectors} grid; truncating to {max_payload} bytes")
            payload_bytes = payload_bytes[:max_payload]
        else:
            raise ValueError(f"Payload too large for {args.rings}x{args.sectors} grid: payload {len(payload_bytes)} bytes, max payload bytes: {max_payload}.")
    def _parse_color(colstr):
        if isinstance(colstr, tuple) and len(colstr) == 3:
            return colstr
        s = colstr.lstrip('#')
        if len(s) == 3:
            s = ''.join([c*2 for c in s])
        if len(s) != 6:
            return (0, 200, 255)
        try:
            return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
        except Exception:
            return (0, 200, 255)

    trans_arg = args.transparent
    make_image(payload_bytes, args.out, rings=args.rings, sectors=args.sectors, size=args.size, quality=args.quality, connect_dots=args.connect_dots, connect_style=args.connect_style, connect_thickness=args.connect_thickness, connect_color=_parse_color(args.connect_color), transparent=trans_arg, hide_ring=args.hide_ring, bank=args.bank)
    print("Wrote:", args.out)


if __name__ == "__main__":
    main()
