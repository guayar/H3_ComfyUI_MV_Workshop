#!/usr/bin/env python3
"""Test zszywania na syntetycznych ujeciach (bez GPU).

Tworzy trzy ujecia z celowymi wadami na szwach:
  ujecie 2: czerwony odcien + jasniejsze + rozmyte
  ujecie 3: zolty odcien + ciemniejsze
Sprawdza:
  1. liczbe klatek wyjsciowych (zgodna ze wzorem),
  2. ze skok jasnosci i chrominancji na szwach po korekcie jest mniejszy niz przed korekta,
  3. ze deflicker nie zwieksza najwiekszego skoku sredniej jasnosci.

Uruchomienie:  python3 scripts/test_stitch.py [folder_roboczy]
"""
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stitch_shots as s  # noqa: E402

W, H, N = 320, 180, 60
FADE, MATCH = 12, 24


def base_scene(seed):
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    grad = 0.25 + 0.5 * x / W
    checker = 0.08 * (((x // 16) + (y // 16)) % 2)
    noise = rng.normal(0, 0.02, (H, W)).astype(np.float32)
    img = np.stack([grad + checker, 0.5 + 0.1 * np.sin(y / 9), 0.6 - grad * 0.3], axis=-1) + noise[..., None]
    return np.clip(img, 0, 1)


def blur(img):
    return s.box_blur(img, passes=3)


def make_shot(folder, scene, tint, bright, do_blur, frames):
    os.makedirs(folder, exist_ok=True)
    for i in range(frames):
        drift = 0.002 * i  # lagodny dryf, realistyczny dla jednego ujecia
        img = scene + drift
        img = img * np.array(tint, dtype=np.float32) + bright
        if do_blur:
            img = blur(img)
        Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(
            os.path.join(folder, f"frame_{i:06d}.png"))


def mean_L(folder_path):
    return float(s.srgb_to_lab(s.load_frame(folder_path))[..., 0].mean())


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.getcwd(), "stitch_test")
    if os.path.exists(root):
        shutil.rmtree(root)
    scene = base_scene(1)
    shots = [os.path.join(root, f"shot_{k}") for k in (1, 2, 3)]
    make_shot(shots[0], scene, (1.0, 1.0, 1.0), 0.0, False, N)
    make_shot(shots[1], scene, (1.15, 0.97, 0.95), 0.08, True, N)
    make_shot(shots[2], scene, (1.0, 1.0, 0.8), -0.05, False, N)

    out_plain = os.path.join(root, "out_plain")
    out_fixed = os.path.join(root, "out_fixed")
    n_plain, rep_plain = s.stitch(shots, out_plain, FADE, 0, 0.15, False,
                                  os.path.join(root, "rep_plain.json"))
    n_fixed, rep_fixed = s.stitch(shots, out_fixed, FADE, MATCH, 0.15, True,
                                  os.path.join(root, "rep_fixed.json"))

    keep = max(FADE, MATCH, 1)
    expected_total = (N - keep) + 2 * (N - FADE) + keep
    print("klatki wyjsciowe:", n_fixed, "oczekiwane:", expected_total)
    assert n_fixed == expected_total, "zla liczba klatek"

    print("\nSzwy bez korekty (match-window=0):")
    for j in rep_plain["joins"]:
        print("  ", j["shot"], j["before"])
    print("Szwy z korekta (match-window=%d, sharpen):" % MATCH)
    for j in rep_fixed["joins"]:
        print("  ", j["shot"], "przed:", j["before"], "\n      po:   ", j["after"])

    before = rep_fixed["joins"]
    for j in before:
        assert j["after"]["L_jump"] <= j["before"]["L_jump"] + 1e-6, f"jasnosc nie poprawila sie na szwie {j['shot']}"
        assert j["after"]["chroma_jump"] <= j["before"]["chroma_jump"] + 1e-6, f"kolor nie poprawil sie na szwie {j['shot']}"
    print("\nOK: skoki L i chrominancji na szwach zmniejszone.")

    # deflicker: nie moze zwiekszyc najwiekszego skoku sredniej jasnosci
    out_def = os.path.join(root, "out_deflicker")
    shutil.copytree(out_fixed, out_def)
    d = s.deflicker(out_def, 9)
    print("deflicker:", d)
    assert d["mean_L_after_max_step"] <= d["mean_L_before_max_step"] + 1e-6, "deflicker pogorszyl ciag"
    print("OK: deflicker nie pogorszyl ciagu.")

    with open(os.path.join(root, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump({"frames": n_fixed, "joins_fixed": rep_fixed["joins"], "deflicker": d}, fh, indent=2)
    print("\nWszystkie testy OK. Folder:", root)


if __name__ == "__main__":
    main()
