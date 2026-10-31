#!/usr/bin/env python3
"""Testy dynamicznej maski klapy (P3): ksztalt, liczba klatek, monotonicznosc, warianty A-D.

Uruchomienie: python3 scripts/test_flap_mask.py [folder_roboczy]
"""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import make_control as mc  # noqa: E402
import stitch_shots as s  # noqa: E402

H, W = 180, 320
FRAMES = 124


def make_plate(path):
    yy, xx = np.mgrid[0:H, 0:W]
    img = np.stack([(xx % 40) / 40.0, (yy % 30) / 30.0, 0.5 + 0.2 * np.sin(xx / 17.0)], axis=-1)
    img = np.clip(img, 0, 1).astype(np.float32)
    Image.fromarray((img * 255).astype(np.uint8)).save(path)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "flap_test")
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    plate = os.path.join(root, "plate.png")
    make_plate(plate)
    out = os.path.join(root, "demo")
    rect = (60, 100, 80, 50)
    summ = mc.flap_sequence(plate, out, rect, FRAMES, stem_max=50.0)
    per = json.load(open(os.path.join(out, "flap_summary.json"), encoding="utf-8"))["per_frame"]

    # 1. liczba klatek i warianty
    for d in ("A_geometry", "B_mask_source", "C_combined", "D_baseline"):
        assert os.path.isdir(os.path.join(out, d)), d
    assert len(os.listdir(os.path.join(out, "A_geometry"))) == FRAMES
    assert len(os.listdir(os.path.join(out, "B_mask_source"))) == 2 * FRAMES  # maska + zrodlo
    assert len(os.listdir(os.path.join(out, "C_combined"))) == 3 * FRAMES      # kontrola + maska + zrodlo
    print("OK 1: 124 klatek, warianty A-D na miejscu")

    # 2. maska binarna i zgodna z zapisem
    m0 = np.asarray(Image.open(os.path.join(out, "B_mask_source", f"mask_frame_{1:06d}.png")))
    assert set(np.unique(m0)).issubset({0, 255}), np.unique(m0)
    print("OK 2: maska binarna 0/255")

    # 3. klapa maleje (skrot), lodyga rosnie (monotonicznie)
    flap = [r["flap_px"] for r in per]
    stem = [r["stem_px"] for r in per]
    assert all(b <= a + 1 for a, b in zip(flap, flap[1:])), "klapa nie maleje monotonicznie"
    assert all(b >= a for a, b in zip(stem, stem[1:])), "lodyga nie rosnie monotonicznie"
    assert stem[0] == 0 and stem[-1] > 0
    print(f"OK 3: klapa {flap[0]} -> {flap[-1]} px, lodyga {stem[0]} -> {stem[-1]} px")

    # 4. zrodlo identyczne we wszystkich klatkach
    src0 = np.asarray(Image.open(os.path.join(out, "B_mask_source", f"source_frame_{1:06d}.png")))
    src_last = np.asarray(Image.open(os.path.join(out, "B_mask_source", f"source_frame_{FRAMES:06d}.png")))
    assert np.array_equal(src0, src_last)
    print("OK 4: zrodlo (plan) niezmienne")

    # 5. wariant A: sterowanie zawiera kontur klapy w ostatniej klatce, B ma maske, D nie ma plikow
    ctrl_last = np.asarray(Image.open(os.path.join(out, "A_geometry", f"frame_{FRAMES:06d}.png")))
    assert (ctrl_last > 0).sum() > 0
    assert os.listdir(os.path.join(out, "D_baseline")) == ["README.txt"]
    print("OK 5: sterowanie niepuste, D bez plikow sterowania")

    # 6. podglad i podsumowanie
    assert os.path.exists(os.path.join(out, "preview_contact_sheet.png"))
    assert os.path.exists(os.path.join(out, "preview_control.gif"))
    print("OK 6: podglad (PNG + GIF) zapisany")
    print("\nWszystkie testy klapy OK. Folder:", root)


if __name__ == "__main__":
    main()
