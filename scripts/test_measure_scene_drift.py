#!/usr/bin/env python3
"""Testy pomiaru dryfu na syntetycznej scenie ze znanymi przeksztalceniami.

Przypadki: tozsamosc, przesuniecie, obrot+skala, zmiana jasnosci, rozmycie,
poruszajacy sie obiekt (z maska i bez), oczekiwany ruch (dolly).
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import measure_scene_drift as m  # noqa: E402

H, W = 240, 320
ROIS = [{"name": "window", "x": 40, "y": 30, "w": 120, "h": 90},
        {"name": "wall", "x": 180, "y": 100, "w": 100, "h": 80}]


def scene(seed=3):
    rng = np.random.default_rng(seed)
    base = rng.random((H, W)).astype(np.float32)
    # wygladzony szum daje strukture z krawedziami, jak fakturę sciany
    for _ in range(3):
        base = m.bilinear(base, *np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64)))[0]
        base = (base + np.roll(base, 1, 0) + np.roll(base, 1, 1)) / 3.0
    # dodatkowe ostre krawedzie
    yy, xx = np.mgrid[0:H, 0:W]
    base += 0.3 * (((xx // 24) + (yy // 18)) % 2)
    base = (base - base.min()) / (base.max() - base.min() + 1e-9)
    rgb = np.stack([base, base * 0.8 + 0.1, base * 0.6 + 0.2], axis=-1).astype(np.float32)
    return np.clip(rgb, 0, 1)


def warp(img_rgb, A, t):
    """Obraz 'po ruchu': punkt p sceny pojawia sie w q = A p + t."""
    Ainv = np.linalg.inv(np.array(A, dtype=np.float64))
    Y, X = np.mgrid[0:H, 0:W].astype(np.float64)
    qx, qy = X - t[0], Y - t[1]
    px = Ainv[0, 0] * qx + Ainv[0, 1] * qy
    py = Ainv[1, 0] * qx + Ainv[1, 1] * qy
    out = np.zeros_like(img_rgb)
    for c in range(3):
        out[..., c], _ = m.bilinear(img_rgb[..., c], px, py)
    return out


def rot_scale(theta_deg, scale):
    th = math.radians(theta_deg)
    c, s = math.cos(th) * scale, math.sin(th) * scale
    return [[c, -s], [s, c]]


def measure(cur_rgb, excl=None):
    ref = scene()
    rows = m.measure_frame(ref, m.luma(ref), cur_rgb, m.luma(cur_rgb), ROIS, excl)
    return rows


def check(name, got, want, tol):
    ok = abs(got - want) <= tol
    print(f"{'OK' if ok else 'FAIL'} {name}: zmierzono {got:.4f}, oczekiwano {want:.4f} (tol {tol})")
    assert ok, name


def main():
    ref = scene()

    # 1. tozsamosc
    r = measure(ref)
    check("tozsamosc: skala", r["consensus"]["scale"], 1.0, 0.002)
    check("tozsamosc: przesuniecie", abs(r["consensus"]["tx"]) + abs(r["consensus"]["ty"]), 0.0, 0.1)

    # 2. przesuniecie
    cur = warp(ref, [[1, 0], [0, 1]], (3.5, -2.25))
    r = measure(cur)
    check("przesuniecie tx", r["consensus"]["tx"], 3.5, 0.15)
    check("przesuniecie ty", r["consensus"]["ty"], -2.25, 0.15)

    # 3. obrot 1 stopien i skala 1.01
    cur = warp(ref, rot_scale(1.0, 1.01), (0.0, 0.0))
    r = measure(cur)
    check("skala 1.01", r["consensus"]["scale"], 1.01, 0.003)
    check("obrot 1 deg", r["consensus"]["rot_deg"], 1.0, 0.15)

    # 4. zmiana jasnosci i kontrastu (korelacja nie powinna zmieniac wyniku)
    cur = np.clip(ref * 1.2 + 0.1, 0, 1)
    r = measure(cur)
    check("jasnosc: skala", r["consensus"]["scale"], 1.0, 0.002)
    check("jasnosc: przesuniecie", abs(r["consensus"]["tx"]) + abs(r["consensus"]["ty"]), 0.0, 0.1)

    # 5. rozmycie (zmiana ostrosci nie przesuwa geometrii)
    cur = ref.copy()
    for _ in range(2):
        cur = (cur + np.roll(cur, 1, 0) + np.roll(cur, -1, 0) + np.roll(cur, 1, 1) + np.roll(cur, -1, 1)) / 5.0
    r = measure(cur)
    check("rozmycie: przesuniecie", abs(r["consensus"]["tx"]) + abs(r["consensus"]["ty"]), 0.0, 0.2)

    # 6. poruszajacy sie obiekt w ROI (bez maski): odporne wazenie ma ograniczyc blad
    cur = warp(ref, [[1, 0], [0, 1]], (2.0, 1.0))
    cur[40:70, 60:110] = 0.95  # jasny prostokat w oknie
    r = measure(cur)
    check("obiekt bez maski: tx", r["consensus"]["tx"], 2.0, 0.4)
    check("obiekt bez maski: ty", r["consensus"]["ty"], 1.0, 0.4)

    # 7. ten sam obiekt z maska wykluczenia: wynik ma byc dokladniejszy
    excl = np.zeros((H, W, 3), dtype=np.float32)
    excl[40:70, 60:110] = 1.0
    r2 = measure(cur, excl)
    check("obiekt z maska: tx", r2["consensus"]["tx"], 2.0, 0.2)
    check("obiekt z maska: ty", r2["consensus"]["ty"], 1.0, 0.2)

    # 8. oczekiwany ruch (dolly): skala 1.02 zgodna z oczekiwaniem -> dryf ~0
    cur = warp(ref, rot_scale(0.0, 1.02), (0.0, 0.0))
    met = m.measure_frame(ref, m.luma(ref), cur, m.luma(cur), ROIS, None)
    j = m.judge(met, {"scale": 1.02, "rot_deg": 0.0, "tx": 0.0, "ty": 0.0})
    check("dolly zgodny z oczekiwaniem: dryf skali", j["drift"]["scale"], 0.0, 0.003)
    assert "scale" not in j["flags"], j["flags"]
    print("OK dolly: brak flagi skali przy oczekiwanym ruchu")

    # 9. dryf bez oczekiwania jest flagowany
    j2 = m.judge(met, None)
    assert "scale" in j2["flags"], j2["flags"]
    print("OK dryf bez oczekiwania: flagowany jako", j2["flags"])

    # 10. ostrosc i R/G sa raportowane
    r = measure(ref)
    assert r["rois"][0]["lapvar"] > 0 and "rg_ratio" in r["rois"][0]
    print("OK raport zawiera lapvar i rg_ratio")
    print("\nWszystkie testy pomiaru dryfu OK (progi sa prowizoryczne).")


if __name__ == "__main__":
    main()
