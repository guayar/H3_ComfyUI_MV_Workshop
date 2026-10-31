#!/usr/bin/env python3
"""Pomiar dryfu geometrii sceny: rejestracja affine (ECC-podobna) na statycznych ROI.

Tylko statyczne elementy architektury (okno, kominek, porecz schodow, gorna sciana).
Ruchome elementy (kafle, rosliny, postac) wyklucza sie maska --exclude-mask
oraz ich wplyw tlumi wazenie odporne (Cauchy) w kazdej iteracji.

Metoda (numpy, bez OpenCV): Gauss-Newton dla przeksztalcenia affine [a11 a12 a21 a22 tx ty]
na znormalizowanych obrazach, z piramida 2 poziomow. Kryterium: korelacja, nie roznica
bezwzgledna, wiec zmiana jasnosci/kontrastu nie zmienia wyniku.

Co raportuje (na klatke):
  * parametry affine per ROI i konsensus (mediana po ROI): skala, obrot, przesuniecie
  * residual_local_px: najwieksze odchylenie przesuniecia jednego ROI od konsensusu
  * confidence (korelacja) i liczbe wazonych pikseli
  * ostrosc (wariancja Laplace'a) na ROI po rejestracji, stosunek do klatki referencyjnej
  * stosunek R/G na ROI (kontrola dryfu koloru)
  * drift = pomiar minus oczekiwany ruch (--expected), domyslnie tozsamosc

Progi tolerancji (PROWIZORYCZNE, [UNVERIFIED] na H3, do kalibracji na planie):
  skala |s-1| <= 0.002, przesuniecie <= 0.5 px, residual_local <= 0.5 px, confidence >= 0.95
Wartosci zmierzone sa osobno w raporcie.

Uzycie:
  python3 scripts/measure_scene_drift.py --frames-dir shot_01 --rois rois.json \
      --exclude-mask moving_mask.png --out drift_shot_01.json
rois.json: [{"name": "window", "x": 120, "y": 40, "w": 200, "h": 150}, ...]  (piksele klatki referencyjnej)
"""
import argparse
import glob
import json
import math
import os
import sys

import numpy as np
from PIL import Image

PROVISIONAL_TOL = {"scale_abs": 0.002, "shift_px": 0.5, "residual_local_px": 0.5, "confidence_min": 0.95}


# ---------- obrazy i probkowanie ----------
def load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def luma(rgb):
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def downsample2(img):
    h, w = img.shape[:2]
    h2, w2 = h // 2 * 2, w // 2 * 2
    v = img[:h2, :w2]
    return v.reshape(h2 // 2, 2, w2 // 2, 2, *img.shape[2:]).mean(axis=(1, 3))


def bilinear(img, qx, qy):
    """Probkowanie dwuliniowe; zwraca wartosci i maske poprawnosci (wewnatrz obrazu)."""
    h, w = img.shape[:2]
    valid = (qx >= 0) & (qx <= w - 1) & (qy >= 0) & (qy <= h - 1)
    x = np.clip(qx, 0, w - 1.000001)
    y = np.clip(qy, 0, h - 1.000001)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = x - x0
    fy = y - y0
    v = (img[y0, x0] * ((1 - fx) * (1 - fy))
         + img[y0, x0 + 1] * (fx * (1 - fy))
         + img[y0 + 1, x0] * ((1 - fx) * fy)
         + img[y0 + 1, x0 + 1] * (fx * fy))
    return v, valid


def gradients(img):
    gy, gx = np.gradient(img)
    return gx, gy


# ---------- rejestracja affine ----------
def _register_level(T, I, Tmask, theta, origin=(0.0, 0.0), iters=40, eps=1e-5):
    """Gauss-Newton; T: szablon (ROI), I: obraz celu, theta = [a11,a12,a21,a22,tx,ty] w pikselach tego poziomu."""
    h, w = T.shape
    Y, X = np.mgrid[0:h, 0:w].astype(np.float64)
    # wspolrzedne w pelnym kadrze: lokalne + poczatek ROI (na tym poziomie piramidy)
    X = X + origin[0]
    Y = Y + origin[1]
    gxI, gyI = gradients(I)
    theta = theta.astype(np.float64).copy()
    last_cost = np.inf
    for _ in range(iters):
        a11, a12, a21, a22, tx, ty = theta
        qx = a11 * X + a12 * Y + tx
        qy = a21 * X + a22 * Y + ty
        Iw, valid = bilinear(I, qx, qy)
        gxw, _ = bilinear(gxI, qx, qy)
        gyw, _ = bilinear(gyI, qx, qy)
        m = valid & (Tmask > 0.5)
        if m.sum() < 50:
            return theta, 0.0, int(m.sum()), False
        t_vals = T[m]
        i_vals = Iw[m]
        tn = (t_vals - t_vals.mean()) / (t_vals.std() + 1e-9)
        s_i = i_vals.std() + 1e-9
        inn = (i_vals - i_vals.mean()) / s_i
        e = inn - tn
        # wagi odporne (Cauchy): piksele ruchomych obiektow dostaja mala wage
        scale_r = 1.4826 * np.median(np.abs(e - np.median(e))) + 1e-6
        wgt = 1.0 / (1.0 + (e / (2.0 * scale_r)) ** 2)
        jx = (gxw[m] / s_i)
        jy = (gyw[m] / s_i)
        xm, ym = X[m], Y[m]
        J = np.stack([jx * xm, jx * ym, jy * xm, jy * ym, jx, jy], axis=1)
        JW = J * wgt[:, None]
        H = J.T @ JW + 1e-9 * np.eye(6)
        g = JW.T @ e
        try:
            dtheta = -np.linalg.solve(H, g)
        except np.linalg.LinAlgError:
            return theta, 0.0, int(m.sum()), False
        theta += dtheta
        cost = float(np.mean(wgt * e * e))
        if np.linalg.norm(dtheta) < eps:
            break
        last_cost = cost
    corr = float(np.mean(tn * inn))
    return theta, corr, int(m.sum()), True


def register_affine(T_full, I_full, Tmask_full, origin=(0.0, 0.0), levels=2):
    """Rejestracja affine na piramidzie. origin = polozenie szablonu w pelnym kadrze.
    Zwraca theta w wspolrzednych PELNEGO kadru, korelacje, liczbe pikseli."""
    pyr = [(T_full, I_full, Tmask_full)]
    for _ in range(levels):
        T, I, M = pyr[-1]
        if min(T.shape) < 24:
            break
        pyr.append((downsample2(T), downsample2(I), downsample2(M)))
    theta = np.array([1, 0, 0, 1, 0, 0], dtype=np.float64)
    corr, npx = 0.0, 0
    for lvl in range(len(pyr) - 1, -1, -1):
        T, I, M = pyr[lvl]
        f = 2 ** lvl
        th = theta.copy()
        th[4] /= f
        th[5] /= f
        origin_l = (origin[0] / f, origin[1] / f)
        th, corr, npx, ok = _register_level(T, I, M, th, origin=origin_l)
        th[4] *= f
        th[5] *= f
        theta = th
    return theta, corr, npx


# ---------- metryki ----------
def theta_metrics(theta):
    a11, a12, a21, a22, tx, ty = theta
    det = a11 * a22 - a12 * a21
    rot = math.degrees(math.atan2(a21 - a12, a11 + a22)) if (abs(a11 + a22) + abs(a21 - a12)) > 0 else 0.0
    return {"scale": round(math.sqrt(abs(det)), 6), "rot_deg": round(rot, 4),
            "tx": round(float(tx), 3), "ty": round(float(ty), 3),
            "a": [round(float(v), 6) for v in (a11, a12, a21, a22)]}


def laplacian_var_roi(gray):
    lap = 4 * gray[1:-1, 1:-1] - gray[:-2, 1:-1] - gray[2:, 1:-1] - gray[1:-1, :-2] - gray[1:-1, 2:]
    return float(lap.var())


def rg_ratio(rgb_roi):
    r = float(rgb_roi[..., 0].mean())
    g = float(rgb_roi[..., 1].mean()) + 1e-9
    return r / g


def measure_frame(ref_rgb, ref_luma, cur_rgb, cur_luma, rois, excl_mask):
    """Zwraca slownik metryk dla jednej klatki wzgledem referencji."""
    per_roi = []
    if excl_mask is not None and excl_mask.ndim == 3:
        excl_mask = excl_mask[..., 0]  # maska moze byc RGB; uzywamy kanalu R
    for roi in rois:
        x, y, w, h = roi["x"], roi["y"], roi["w"], roi["h"]
        T = ref_luma[y:y + h, x:x + w]
        Tm = np.ones_like(T)
        if excl_mask is not None:
            Tm = (excl_mask[y:y + h, x:x + w] < 0.5).astype(np.float32)
        theta_full, corr, npx = register_affine(T, cur_luma, Tm, origin=(float(x), float(y)))
        m = theta_metrics(theta_full)
        # ostrosc i R/G po rejestracji (probkowanie ROI z klatki bieżącej)
        Y, X = np.mgrid[y:y + h, x:x + w].astype(np.float64)
        qx = theta_full[0] * X + theta_full[1] * Y + theta_full[4]
        qy = theta_full[2] * X + theta_full[3] * Y + theta_full[5]
        cur_roi_luma, valid = bilinear(cur_luma, qx, qy)
        ref_roi_luma = ref_luma[y:y + h, x:x + w]
        g_rgb = np.stack([bilinear(cur_rgb[..., c], qx, qy)[0] for c in range(3)], axis=-1)
        per_roi.append({
            "name": roi["name"], **m,
            "confidence": round(corr, 4), "valid_px": npx,
            "lapvar": round(laplacian_var_roi(cur_roi_luma), 6),
            "lapvar_ref": round(laplacian_var_roi(ref_roi_luma), 6),
            "rg_ratio": round(rg_ratio(g_rgb[valid] if valid.any() else g_rgb.reshape(-1, 3)[None]), 5),
        })

    scales = np.array([r["scale"] for r in per_roi])
    rots = np.array([r["rot_deg"] for r in per_roi])
    txs = np.array([r["tx"] for r in per_roi])
    tys = np.array([r["ty"] for r in per_roi])
    cons = {"scale": round(float(np.median(scales)), 6), "rot_deg": round(float(np.median(rots)), 4),
            "tx": round(float(np.median(txs)), 3), "ty": round(float(np.median(tys)), 3)}
    resid = [round(float(math.hypot(r["tx"] - cons["tx"], r["ty"] - cons["ty"])), 3) for r in per_roi]
    return {"consensus": cons, "residual_local_px": max(resid) if resid else 0.0,
            "rois": per_roi, "min_confidence": min(r["confidence"] for r in per_roi)}


def judge(metrics, expected):
    """Dryf = pomiar minus oczekiwany ruch. Wynik z progami PROWIZORYCZNYMI."""
    e = expected or {"scale": 1.0, "rot_deg": 0.0, "tx": 0.0, "ty": 0.0}
    c = metrics["consensus"]
    drift = {"scale": round(c["scale"] - e["scale"], 6), "rot_deg": round(c["rot_deg"] - e["rot_deg"], 4),
             "tx": round(c["tx"] - e["tx"], 3), "ty": round(c["ty"] - e["ty"], 3)}
    shift = math.hypot(drift["tx"], drift["ty"])
    flags = []
    if abs(drift["scale"]) > PROVISIONAL_TOL["scale_abs"]:
        flags.append("scale")
    if shift > PROVISIONAL_TOL["shift_px"]:
        flags.append("shift")
    if metrics["residual_local_px"] > PROVISIONAL_TOL["residual_local_px"]:
        flags.append("residual_local")
    if metrics["min_confidence"] < PROVISIONAL_TOL["confidence_min"]:
        flags.append("low_confidence")
    return {"drift": drift, "shift_px": round(shift, 3), "flags": flags}


def run(frames_dir, rois, excl_mask_path, expected_map, max_frames, ref_index=0):
    files = sorted(glob.glob(os.path.join(frames_dir, "*.png")))[:max_frames]
    if not files:
        sys.exit(f"brak klatek w {frames_dir}")
    ref_rgb = load_rgb(files[ref_index])
    ref_l = luma(ref_rgb)
    excl = None
    if excl_mask_path:
        excl = luma(load_rgb(excl_mask_path))
    out = []
    for idx, f in enumerate(files):
        cur = load_rgb(f)
        met = measure_frame(ref_rgb, ref_l, cur, luma(cur), rois, excl)
        exp = expected_map.get(idx) if expected_map else None
        out.append({"frame": idx, "file": os.path.basename(f), **met, **judge(met, exp)})
    return out


def summarise(rows):
    if not rows:
        return {}
    return {
        "frames": len(rows),
        "max_abs_scale_drift": max(abs(r["drift"]["scale"]) for r in rows),
        "max_shift_px": max(r["shift_px"] for r in rows),
        "max_residual_local_px": max(r["residual_local_px"] for r in rows),
        "min_confidence": min(r["min_confidence"] for r in rows),
        "frames_flagged": sum(1 for r in rows if r["flags"]),
        "tolerance_provisional": PROVISIONAL_TOL,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames-dir", required=True)
    ap.add_argument("--rois", required=True, help="JSON z listą ROI (piksele klatki referencyjnej)")
    ap.add_argument("--exclude-mask", help="PNG: biale = ruchome elementy, pomijane w szablonie")
    ap.add_argument("--expected", help="JSON: {\"<idx>\": {\"scale\":..,\"rot_deg\":..,\"tx\":..,\"ty\":..}} (np. dolly)")
    ap.add_argument("--max-frames", type=int, default=10 ** 9)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    rois = json.load(open(args.rois, encoding="utf-8"))
    expected = None
    if args.expected:
        expected = {int(k): v for k, v in json.load(open(args.expected, encoding="utf-8")).items()}
    rows = run(args.frames_dir, rois, args.exclude_mask, expected, args.max_frames)
    report = {"summary": summarise(rows), "frames": rows,
              "note": "[CODE] pomiar numpy-ECC; progi PROWIZORYCZNE, skalibrowac na planie"}
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print("raport:", args.out)


if __name__ == "__main__":
    main()
