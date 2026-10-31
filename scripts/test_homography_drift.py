#!/usr/bin/env python3
"""Testy trybu homografii pomiaru dryfu (perspektywa h31, h32) na syntetycznej scenie.

1. tozsamosc: h31, h32 ~ 0
2. znana perspektywa: h31, h32 odzyskane w granicach 25 % (lub 1e-5 absolutnie)
3. przesuniecie w srodku ROI zgadza sie z linearyzacja prawdziwej homografii (<= 0,3 px)
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_scene_drift as m  # noqa: E402
import test_measure_scene_drift as t  # noqa: E402

ROIS = t.ROIS


def warp_h(img, H):
    """Obraz po ruchu homograficznym: punkt p sceny pojawia sie w q = H(p)."""
    Hi = np.linalg.inv(H)
    Y, X = np.mgrid[0:t.H, 0:t.W].astype(np.float64)
    D = Hi[2, 0] * X + Hi[2, 1] * Y + Hi[2, 2]
    px = (Hi[0, 0] * X + Hi[0, 1] * Y + Hi[0, 2]) / D
    py = (Hi[1, 0] * X + Hi[1, 1] * Y + Hi[1, 2]) / D
    out = np.zeros_like(img)
    for c in range(3):
        out[..., c], _ = m.bilinear(img[..., c], px, py)
    return out


def main():
    ref = t.scene()
    luma = m.luma(ref)

    # 1. tozsamosc
    met = m.measure_frame(ref, luma, ref, luma, ROIS, None, model="homography")
    p = met["rois"][0]["perspective_h31_h32"]
    assert abs(p[0]) < 1e-5 and abs(p[1]) < 1e-5, p
    print("OK 1: tozsamosc -> perspektywa ~0", p)

    # 2. znana perspektywa
    H_true = np.array([[1.0, 0.0, 2.0], [0.0, 1.0, -1.0], [3e-4, -2e-4, 1.0]])
    cur = warp_h(ref, H_true)
    cur_l = m.luma(cur)
    met = m.measure_frame(ref, luma, cur, cur_l, ROIS, None, model="homography")
    for roi_res in met["rois"]:
        h31, h32 = roi_res["perspective_h31_h32"]
        assert abs(h31 - 3e-4) <= 0.25 * 3e-4 + 1e-5, ("h31", h31)
        assert abs(h32 - (-2e-4)) <= 0.25 * 2e-4 + 1e-5, ("h32", h32)
    print("OK 2: perspektywa odzyskana:", met["rois"][0]["perspective_h31_h32"])

    # 3. przesuniecie w srodku ROI vs linearyzacja prawdziwej homografii
    for roi, res in zip(ROIS, met["rois"]):
        cx, cy = roi["x"] + roi["w"] / 2.0, roi["y"] + roi["h"] / 2.0
        exp = m.homography_to_affine_at(H_true, cx, cy)
        assert abs(res["tx"] - exp[4]) <= 0.3, (res["name"], res["tx"], exp[4])
        assert abs(res["ty"] - exp[5]) <= 0.3, (res["name"], res["ty"], exp[5])
        print(f"OK 3: {res['name']} tx {res['tx']:.3f} vs {exp[4]:.3f}, ty {res['ty']:.3f} vs {exp[5]:.3f}")

    # 4. tryb affine nie zwraca perspektywy (zgodnosc wsteczna)
    met_a = m.measure_frame(ref, luma, cur, cur_l, ROIS, None, model="affine")
    assert "perspective_h31_h32" not in met_a["rois"][0]
    print("OK 4: tryb affine bez zmian (brak pola perspektywy)")
    print("\nWszystkie testy homografii OK.")


if __name__ == "__main__":
    main()
