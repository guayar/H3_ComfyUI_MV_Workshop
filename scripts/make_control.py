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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate", help="obraz planu lokacji (PNG)")
    ap.add_argument("--frames", type=int, default=243, help="liczba klatek (17n+5, np. 243)")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--percentile", type=float, default=88.0, help="prog krawedzi w percentylach (wyzej = mniej krawedzi)")
    ap.add_argument("--thicken", type=int, default=1, help="ile razy pogrubic krawedzie o 1 px")
    ap.add_argument("--out", help="plik MP4 (np. ComfyUI/input/control_shot_01.mp4)")
    ap.add_argument("--png-dir", help="folder na klatki PNG (opcjonalnie)")
    args = ap.parse_args()
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
