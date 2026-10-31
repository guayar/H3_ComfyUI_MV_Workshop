#!/usr/bin/env python3
"""Testy rozmycia calego ujecia (P4): sigma z binarnego podzialu, kierunek, ruchomy pierwszy plan.

Przypadki:
  1. rozmycie Gaussa obniza wariancje Laplace'a, sigma=0 jest tozsamoscia
  2. find_blur_sigma trafia w cel (blad <= 5 %)
  3. nowe ujecie OSTRZEJSZE -> blur_match rozmywa je i zbliza ostrosc do poprzedniego
  4. nowe ujecie MIEKSZE -> blur_match nic nie robi (sigma = 0)
  5. ruchomy obiekt POZA gornym pasem nie zmienia sigmy
  6. sigma jest jedna dla calego ujecia (zapisana raz w raporcie)
"""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stitch_shots as s  # noqa: E402

H, W, N = 180, 320, 60
FADE, MATCH, BAND = 12, 24, 0.15


def texture(seed=7):
    rng = np.random.default_rng(seed)
    base = rng.random((H, W, 3)).astype(np.float32)
    yy, xx = np.mgrid[0:H, 0:W]
    base[..., 0] += 0.25 * (((xx // 6) + (yy // 6)) % 2)
    return np.clip(base / base.max(), 0, 1).astype(np.float32)


def write_shot(folder, frames_rgb, moving=None):
    os.makedirs(folder, exist_ok=True)
    for i in range(N):
        img = frames_rgb.copy()
        if moving is not None:
            # poruszajacy sie jasny prostokat w dolnej czesci kadru (poza gornym pasem)
            x0 = 20 + (i * 3) % 200
            img[120:150, x0:x0 + 40] = 0.97
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            os.path.join(folder, f"frame_{i:06d}.png"))


def run_stitch(root, shots, tag, blur):
    out = os.path.join(root, f"out_{tag}")
    rep = os.path.join(root, f"rep_{tag}.json")
    n, report = s.stitch(shots, out, FADE, MATCH, BAND, False, rep, blur_match=blur)
    return n, report


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "blur_test")
    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    sharp = texture()
    soft = s.gaussian_blur(sharp, 1.6)

    # 1. rozmycie obniza wariancje; sigma 0 = tozsamosc
    v_sharp = s.top_band_lapvar(sharp, BAND)
    v_soft = s.top_band_lapvar(s.gaussian_blur(sharp, 1.0), BAND)
    assert s.gaussian_blur(sharp, 0.0) is sharp
    assert v_soft < v_sharp
    print(f"OK 1: rozmycie obniza wariancje ({v_sharp:.5f} -> {v_soft:.5f}), sigma=0 to tozsamosc")

    # 2. sigma trafia w cel
    target = 0.5 * v_sharp
    sigma, achieved = s.find_blur_sigma(sharp, target, BAND)
    assert abs(achieved - target) / target <= 0.05, (achieved, target)
    print(f"OK 2: find_blur_sigma -> sigma={sigma:.3f}, wariancja {achieved:.5f} vs cel {target:.5f}")

    # 3. nowe ujecie ostrzejsze: poprzednie miekkie (A), nowe ostre (B)
    a_dir = os.path.join(root, "A_soft"); b_dir = os.path.join(root, "B_sharp")
    write_shot(a_dir, soft)
    write_shot(b_dir, sharp)
    n3, rep3 = run_stitch(root, [a_dir, b_dir], "sharper_next", blur=True)
    j = rep3["joins"][0]
    ratio_before = j["before"]["sharp_ratio_head_over_tail"]
    ratio_after = j["after"]["sharp_ratio_head_over_tail"]
    assert ratio_before > 1.2, ratio_before
    assert abs(np.log(ratio_after)) < abs(np.log(ratio_before)) * 0.5, (ratio_before, ratio_after)
    assert j["blur_sigma_whole_shot"] > 0
    print(f"OK 3: ostrzejsze nowe ujecie: stosunek ostrosci {ratio_before:.2f} -> {ratio_after:.2f}, "
          f"sigma={j['blur_sigma_whole_shot']}")

    # 4. nowe ujecie miekkie: blur_match nic nie robi
    c_dir = os.path.join(root, "C_sharp"); d_dir = os.path.join(root, "D_soft")
    write_shot(c_dir, sharp)
    write_shot(d_dir, soft)
    _, rep4 = run_stitch(root, [c_dir, d_dir], "softer_next", blur=True)
    assert rep4["joins"][0]["blur_sigma_whole_shot"] == 0.0
    print("OK 4: miekkie nowe ujecie: blur_match wylaczony (sigma=0)")

    # 5. ruchomy obiekt poza gornym pasem nie zmienia sigmy
    e_dir = os.path.join(root, "E_sharp_moving"); write_shot(e_dir, sharp, moving=True)
    _, rep5 = run_stitch(root, [a_dir, e_dir], "moving_fg", blur=True)
    sigma_moving = rep5["joins"][0]["blur_sigma_whole_shot"]
    assert abs(sigma_moving - j["blur_sigma_whole_shot"]) <= 0.1, (sigma_moving, j["blur_sigma_whole_shot"])
    print(f"OK 5: ruchomy pierwszy plan: sigma {sigma_moving} vs {j['blur_sigma_whole_shot']} bez obiektu")

    # 6. sigma zapisana raz na szew; wszystkie klatki ujecia B przechodza przez to samo rozmycie
    assert "blur_sigma_whole_shot" in rep3["joins"][0]
    assert n3 == (N - max(FADE, MATCH)) + (N - FADE) + max(FADE, MATCH)
    print("OK 6: sigma jednorazowa na szew, liczba klatek zgodna")
    print("\nWszystkie testy rozmycia OK. Folder:", root)


if __name__ == "__main__":
    main()
