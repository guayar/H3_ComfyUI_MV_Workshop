#!/usr/bin/env python3
"""Robi wideo sterujace (krawedzie) z planu lokacji dla Fun ControlNet w H3.

Zalozenie: geometria zestawu musi byc identyczna miedzy ujeciami. Krawedzie planu lokacji
(lukowe sklepienie, okno, schody, kafelki podlogi) trzymaja perspektywe i skale.

Metoda: gradient Sobela na jasnosci, prog po percentylu, lekkie pogrubienie.
Uproszczony odpowiednik Canny (bez histerezy i bez cienkiego szkieletu), wystarczajacy do testu.

Uzycie:
  python3 scripts/make_control.py set_plate.png --frames 243 --fps 24 \
      --out ~/ComfyUI/input/control_shot_01.mp4
  # opcjonalnie klatki PNG do podgladu:
  python3 scripts/make_control.py set_plate.png --frames 243 --png-dir control_frames/

Sterowanie statyczne: wszystkie klatki sa takie same (kamera stoi). Dla ruchomych elementow
(kafle, rosliny) trzeba podac maske i zmieniac kontur klatka po klatce (nie zrobione tutaj).
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stitch_shots as s  # noqa: E402


def sobel_edges(rgb, percentile, thicken):
    """rgb: float32 HxWx3 0..1 -> maska krawedzi (bool HxW)."""
    luma = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
    luma = s.box_blur(luma[..., None], passes=1)[..., 0]
    p = np.pad(luma, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    mag = np.hypot(gx, gy)
    thr = np.percentile(mag, percentile)
    edges = mag > thr
    for _ in range(thicken):
        e = edges
        p = np.pad(e, 1)
        edges = e | p[:-2, 1:-1] | p[2:, 1:-1] | p[1:-1, :-2] | p[1:-1, 2:]
    return edges


# ---------- dynamiczna maska: jedna klapa podlogi + wyrastajaca lodyga (P3) ----------
# [CODE] to tylko przyblizenie 2D (nie fizyka): klapa unosi sie, dolna krawedz skraca sie i przesuwa w gore.
# Nie zaklada, ze H3 odtworzy te fizyke. Wynik trzeba obejrzec i zmierzyc.

def ease(t):
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(t, 0, 1))


def flap_polygon(rect, theta):
    """Czworokat klapy: gorna krawedz (zawias) stala, dolna unosi sie. theta w radianach 0..pi/2."""
    x, y, w, h = rect
    lift = h * 0.2 * np.sin(theta)
    short = h * (1.0 - 0.4 * np.sin(theta))  # skrot dolnej krawedzi: lagodniejszy niz cos(theta)
    inset = w * 0.06 * np.sin(theta)
    return np.array([[x, y], [x + w, y],
                     [x + w - inset, y + short - lift], [x + inset, y + short - lift]], dtype=np.float64)


def poly_mask(poly, H, W):
    """Maska wypuklego czworokata (kolejnosc wierzcholkow zgodna z ruchem wskazowek)."""
    Y, X = np.mgrid[0:H, 0:W].astype(np.float64)
    inside = np.ones((H, W), dtype=bool)
    n = len(poly)
    d1, d2 = poly[1] - poly[0], poly[2] - poly[1]
    sign = np.sign(d1[0] * d2[1] - d1[1] * d2[0])
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        cross = (b[0] - a[0]) * (Y - a[1]) - (b[1] - a[1]) * (X - a[0])
        inside &= (sign * cross) >= 0
    return inside


def stem_mask(base_xy, length, width, H, W):
    """Lodyga pionowa od punktu bazowego w gore o zadanej dlugosci i szerokosci."""
    m = np.zeros((H, W), dtype=bool)
    if length <= 0:
        return m
    bx, by = base_xy
    y0 = int(max(0, by - length))
    y1 = int(min(H, by + 1))
    xs = int(bx - width / 2)
    xe = int(bx + width / 2) + 1
    m[y0:y1, max(0, xs):min(W, xe)] = True
    return m


def outline(mask):
    """Kontur maski (piksele maski, ktore maja sasiada spoza maski)."""
    p = np.pad(mask, 1)
    inner = (p[1:-1, 1:-1] & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:])
    return mask & ~inner


def flap_sequence(plate_path, out_dir, rect, frames, max_angle_deg=62.0, stem_max=0.0, percentile=88.0,
                  thicken=1, preview=True):
    """Zapisuje warianty A-D i podglad. Zwraca slownik z metrykami."""
    plate = s.load_frame(plate_path)
    H, W = plate.shape[:2]
    edges_static = sobel_edges(plate, percentile, thicken)
    x, y, w, h = rect
    base = (x + w / 2.0, float(y))
    max_theta = np.radians(max_angle_deg)
    stats = []
    dirs = {k: os.path.join(out_dir, k) for k in ("A_geometry", "B_mask_source", "C_combined", "D_baseline")}
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)
    frames_store = {"mask": [], "control": [], "source": []}
    for i in range(frames):
        t = i / max(1, frames - 1)
        theta = max_theta * ease(t * 1.0)
        stem_len = stem_max * ease(max(0.0, (t - 0.35) / 0.65))
        poly = flap_polygon(rect, theta)
        m_flap = poly_mask(poly, H, W)
        m_stem = stem_mask(base, stem_len, 6, H, W) if stem_max > 0 else np.zeros((H, W), bool)
        mask = m_flap | m_stem
        # kontrola: krawedzie planu poza maska + kontur klapy i lodygi (ruch sterowania)
        control = (edges_static & ~mask) | outline(m_flap) | outline(m_stem)
        mask_u8 = (mask * 255).astype(np.uint8)
        ctrl_u8 = (control * 255).astype(np.uint8)
        frames_store["mask"].append(mask_u8)
        frames_store["control"].append(ctrl_u8)
        stats.append({"frame": i, "theta_deg": round(float(np.degrees(theta)), 3),
                      "stem_px": int(m_stem.sum()), "flap_px": int(m_flap.sum()),
                      "mask_px": int(mask.sum()), "control_px": int(control.sum())})
    source_u8 = (plate * 255).astype(np.uint8)
    # zapis wariantow
    for i in range(frames):
        name = f"frame_{i + 1:06d}.png"
        Image.fromarray(source_u8).save(os.path.join(dirs["B_mask_source"], "source_" + name), compress_level=1)
        Image.fromarray(frames_store["mask"][i]).save(os.path.join(dirs["B_mask_source"], "mask_" + name), compress_level=1)
        Image.fromarray(frames_store["control"][i]).save(os.path.join(dirs["A_geometry"], name), compress_level=1)
        Image.fromarray(frames_store["control"][i]).save(os.path.join(dirs["C_combined"], "control_" + name), compress_level=1)
        Image.fromarray(frames_store["mask"][i]).save(os.path.join(dirs["C_combined"], "mask_" + name), compress_level=1)
        Image.fromarray(source_u8).save(os.path.join(dirs["C_combined"], "source_" + name), compress_level=1)
    # D: bez sterowania; zachowany tylko plik informacyjny
    with open(os.path.join(dirs["D_baseline"], "README.txt"), "w", encoding="utf-8") as fh:
        fh.write("Wariant D: brak ControlNet (baseline Ref2VA). Brak plikow sterowania.\n")

    if preview:
        n = min(8, frames)
        idxs = np.linspace(0, frames - 1, n).astype(int)
        tiles = []
        for i in idxs:
            tile = np.stack([frames_store["control"][i]] * 3, axis=-1).astype(np.uint8)
            mk = frames_store["mask"][i] > 127
            tile[mk, 0] = np.maximum(tile[mk, 0], 180)
            tiles.append(Image.fromarray(tile).resize((W // 2, H // 2)))
        sheet = Image.new("RGB", (W // 2 * 4, H // 2 * 2))
        for k, t_img in enumerate(tiles):
            sheet.paste(t_img, ((k % 4) * W // 2, (k // 4) * H // 2))
        sheet.save(os.path.join(out_dir, "preview_contact_sheet.png"))
        gif_frames = [Image.fromarray(np.stack([frames_store["control"][i]] * 3, axis=-1)).resize((W // 2, H // 2))
                      for i in range(0, frames, max(1, frames // 60))]
        gif_frames[0].save(os.path.join(out_dir, "preview_control.gif"), save_all=True,
                           append_images=gif_frames[1:], duration=int(1000 / 12), loop=0)
    summary = {"frames": frames, "max_theta_deg": max_angle_deg, "stem_max_px": stem_max,
               "tiles": ["A_geometry", "B_mask_source", "C_combined", "D_baseline"],
               "stats_first": stats[0], "stats_last": stats[-1],
               "note": "[CODE] przyblizenie 2D klapy; [UNVERIFIED] czy H3 odtworzy ruch"}
    with open(os.path.join(out_dir, "flap_summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"summary": summary, "per_frame": stats}, fh, ensure_ascii=False, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate", help="obraz planu lokacji (PNG)")
    ap.add_argument("--frames", type=int, default=243, help="liczba klatek (17n+5, np. 243)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--percentile", type=float, default=88.0, help="prog krawedzi w percentylach (wyzej = mniej krawedzi)")
    ap.add_argument("--thicken", type=int, default=1, help="ile razy pogrubic krawedzie o 1 px")
    ap.add_argument("--out", help="plik MP4 (np. ComfyUI/input/control_shot_01.mp4)")
    ap.add_argument("--png-dir", help="folder na klatki PNG (opcjonalnie)")
    ap.add_argument("--flap-demo", metavar="DIR", help="dynamiczna maska: klapa + lodyga, warianty A-D i podglad")
    ap.add_argument("--flap-rect", default="60,80,120,60", help="x,y,w,h klapy w pikselach planu")
    ap.add_argument("--flap-frames", type=int, default=124, help="klatki dema (domyslnie 124 = 17n+5)")
    ap.add_argument("--flap-stem", type=int, default=60, help="maks. dlugosc lodygi w pikselach")
    args = ap.parse_args()
    if args.flap_demo:
        rect = tuple(int(v) for v in args.flap_rect.split(","))
        summ = flap_sequence(args.plate, args.flap_demo, rect, args.flap_frames, stem_max=float(args.flap_stem),
                             percentile=args.percentile, thicken=args.thicken)
        print(json.dumps(summ["stats_last"], ensure_ascii=False))
        print(f"zapisano demo klapy w {args.flap_demo} (warianty A-D, podglad, flap_summary.json)")
        return
    if args.frames % 17 != 5:
        ap.error("--frames musi byc w siatce 17n+5")
    if not args.out and not args.png_dir:
        ap.error("podaj --out (MP4) albo --png-dir (PNG)")

    plate = s.load_frame(args.plate)
    mask = sobel_edges(plate, args.percentile, args.thicken)
    frame = np.zeros_like(plate)
    frame[mask] = 1.0  # biale krawedzie na czarnym tle
    frame_u8 = (frame * 255).astype(np.uint8)
    edge_ratio = float(mask.mean())
    print(f"krawedzie: {edge_ratio * 100:.2f} % pikseli")

    if args.png_dir:
        os.makedirs(args.png_dir, exist_ok=True)
        for i in range(args.frames):
            Image.fromarray(frame_u8).save(os.path.join(args.png_dir, f"control_{i + 1:06d}.png"), compress_level=1)
        print(f"zapisano {args.frames} klatek PNG w {args.png_dir}")

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        # ta sama maska w kazdej klatce: podajemy ja przez plik pomocniczy
        tmp = os.path.join(os.path.dirname(os.path.abspath(args.out)), ".control_mask_tmp.png")
        Image.fromarray(frame_u8).save(tmp)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(args.fps),
               "-i", tmp, "-frames:v", str(args.frames),
               "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p",
               "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", args.out]
        subprocess.run(cmd, check=True)
        os.remove(tmp)
        print(f"zapisano wideo sterujace: {args.out}")


if __name__ == "__main__":
    main()
