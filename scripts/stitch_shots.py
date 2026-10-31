#!/usr/bin/env python3
"""Zszywanie ujec (sekwencje PNG) w jeden ciag klatek.

Rozwiazuje na szwach:
  * skok koloru (w tym czerwien/zoltosc) -> dopasowanie srednia i odchyleniem w przestrzeni Lab
    (osobno jasnosc L i chrominancja a/b; sama jasnosc nie wystarcza, patrz docs/STITCH_WORKSHOP.md)
  * skok jasnosci -> ten sam mechanizm (kanal L)
  * skok ostrosci -> opcjonalna wyostrzajaca maska, gdy nowe ujecie jest mieksze
  * przeskok ujecia -> rozplyw (dissolve) z cosinusowym przejsciem alfa
  * dryf koloru/jasnosci wzdluz calego ciagu -> opcjonalny deflicker (wygladzenie sredniej L)
  * kodowanie koncowe ffmpeg z jawnym BT.709 (zeby odtwarzacz nie przesunal kolorow)

Uzycie:
  python3 scripts/stitch_shots.py out_dir shot_01 shot_02 shot_03 \
      --fade 12 --match-window 24 --sharpen --deflicker 9 --encode out.mp4

Kazdy argument shot_XX to folder z klatkami *.png, w kolejnosci wystepowania.
Pamiec: trzymane sa tylko klatki potrzebne do przejsc (max(fade, match-window)), reszta jest zapisywana na biezaco.
"""
import argparse
import glob
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image

# ---------- konwersja kolorow sRGB <-> Lab (D65) ----------
_M = np.array([[0.4124564, 0.3575761, 0.1804375],
               [0.2126729, 0.7151522, 0.0721750],
               [0.0193339, 0.1191920, 0.9503041]], dtype=np.float32)
_M_INV = np.linalg.inv(_M).astype(np.float32)
_WHITE = np.array([0.95047, 1.0, 1.08883], dtype=np.float32)


def srgb_to_lab(rgb):
    """rgb: float32 HxWx3 w zakresie 0..1 -> Lab (L 0..100, a/b ~ -128..127)."""
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    xyz = lin @ _M.T / _WHITE
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16.0 / 116.0)
    L = 116.0 * f[..., 1] - 16.0
    a = 500.0 * (f[..., 0] - f[..., 1])
    b = 200.0 * (f[..., 1] - f[..., 2])
    return np.stack([L, a, b], axis=-1).astype(np.float32)


def lab_to_srgb(lab):
    L, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    fy = (L + 16.0) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    f = np.stack([fx, fy, fz], axis=-1)
    xyz = np.where(f > 0.206897, f ** 3, (f - 16.0 / 116.0) / 7.787) * _WHITE
    lin = np.clip(xyz @ _M_INV.T, 0.0, 1.0)
    srgb = np.where(lin <= 0.0031308, 12.92 * lin, 1.055 * np.power(lin, 1 / 2.4) - 0.055)
    return np.clip(srgb, 0.0, 1.0).astype(np.float32)


# ---------- wczytywanie / zapis ----------
def load_frame(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float32) / 255.0


def save_frame(arr, path):
    Image.fromarray(np.clip(np.round(arr * 255.0), 0, 255).astype(np.uint8)).save(path, compress_level=1)


def list_frames(folder):
    files = sorted(glob.glob(os.path.join(folder, "*.png")))
    if not files:
        sys.exit(f"Brak klatek PNG w {folder}")
    return files


# ---------- statystyki i metryki ----------
def lab_stats(lab_frames):
    """Srednia i odchylenie kazdego kanalu Lab po zbiorze klatek (probkowane co 4. piksel)."""
    samples = np.concatenate([f[::4, ::4].reshape(-1, 3) for f in lab_frames], axis=0)
    return samples.mean(axis=0), samples.std(axis=0) + 1e-6


def laplacian_var(gray, band):
    h = gray.shape[0]
    g = gray[: max(8, int(h * band))]
    lap = 4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:]
    return float(lap.var())


def join_metrics(tail_rgb, head_rgb, band):
    """Metryki na szwie: roznice koloru/jasnosci i stosunek ostrosci gornego pasa."""
    a, b = tail_rgb[-1], head_rgb[0]
    la, lb = srgb_to_lab(a), srgb_to_lab(b)
    ga = la[..., 0]
    gb = lb[..., 0]
    return {
        "rgb_jump_pct": [round(float(abs(a[..., c].mean() - b[..., c].mean())) * 100, 3) for c in range(3)],
        "L_jump": round(float(abs(la[..., 0].mean() - lb[..., 0].mean())), 3),
        "chroma_jump": round(float(np.hypot(la[..., 1].mean() - lb[..., 1].mean(),
                                            la[..., 2].mean() - lb[..., 2].mean())), 3),
        "sharp_ratio_head_over_tail": round(laplacian_var(gb, band) / max(laplacian_var(ga, band), 1e-9), 3),
    }


def cosine_ramp(n):
    """Wagi 1 -> 0 w n krokach (cosinusowo); dla n<=0 pusta tablica."""
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.linspace(0.0, 1.0, n, dtype=np.float32)
    return 0.5 * (1 + np.cos(np.pi * t))


def box_blur(img, passes=2):
    out = img
    for _ in range(passes):
        p = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode="edge")
        out = (p[:-2, :-2] + p[:-2, 1:-1] + p[:-2, 2:] + p[1:-1, :-2] + p[1:-1, 1:-1]
               + p[1:-1, 2:] + p[2:, :-2] + p[2:, 1:-1] + p[2:, 2:]) / 9.0
    return out


def unsharp(rgb, amount):
    if amount <= 0:
        return rgb
    return np.clip(rgb + amount * (rgb - box_blur(rgb)), 0.0, 1.0)


# ---------- rozmycie calego ujecia (P4) ----------
# [CODE] sigma jest jedna dla CALEGO ujecia; nie zmienia sie klatka po klatce (brak migotania).
# Zastepuje wyostrzanie per klatka w trybie blur_match. Nie odtwarza utraconych detali, tylko wyrownuje ostrosc.

def gaussian_blur(rgb, sigma):
    """Rozmycie Gaussa rozdzielne (dwa przebiegi 1D), brzegi z replikacja."""
    if sigma <= 0:
        return rgb
    radius = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-radius, radius + 1, dtype=np.float32)
    k = np.exp(-(x * x) / (2 * sigma * sigma))
    k /= k.sum()
    out = rgb
    for axis in (0, 1):
        pad = [(0, 0)] * 3
        pad[axis] = (radius, radius)
        p = np.pad(out, pad, mode="edge")
        acc = np.zeros_like(out)
        for j, kj in enumerate(k):
            sl = [slice(None)] * 3
            sl[axis] = slice(j, j + out.shape[axis])
            acc += kj * p[tuple(sl)]
        out = acc
    return out


def top_band_lapvar(rgb, band):
    """Wariancja Laplace'a jasnosci w gornym pasie kadru (ta sama metryka co w raporcie szwu)."""
    return laplacian_var(srgb_to_lab(rgb)[..., 0] / 100.0, band)


def find_blur_sigma(sample_rgb, target_var, band, max_sigma=4.0, iters=30):
    """Najmniejsze sigma, ktore sprowadza wariancje Laplace'a gornego pasa do celu.

    Zwraca 0, gdy probka jest juz nie ostrzejsza niz cel. Funkcja jest malejaca w sigma,
    wiec binarny podzial jest poprawny. Zmierzona wariancja po rozmyciu jest zwracana do raportu.
    """
    if top_band_lapvar(sample_rgb, band) <= target_var:
        return 0.0, top_band_lapvar(sample_rgb, band)
    lo, hi = 0.0, max_sigma
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if top_band_lapvar(gaussian_blur(sample_rgb, mid), band) > target_var:
            lo = mid
        else:
            hi = mid
    sigma = 0.5 * (lo + hi)
    return sigma, top_band_lapvar(gaussian_blur(sample_rgb, sigma), band)


# ---------- korekta ujecia ----------
def color_correct(rgb, mu_t, sd_t, mu_s, sd_s, weight):
    """Przeniesie statystyk Lab: target (mu_t, sd_t) z szwu A -> klatka B. weight: 0..1 (1 = pelna korekta)."""
    lab = srgb_to_lab(rgb)
    scale = np.clip(sd_t / sd_s, 0.8, 1.25)
    corr = (lab - mu_s) * scale + mu_t
    lab = lab + weight * (corr - lab)
    return lab_to_srgb(lab)


# ---------- glowna logika ----------
def stitch(shot_dirs, out_dir, fade, match_window, band, sharpen, report_path, blur_match=False):
    """Zszywa ujecia. Kolejnosc zapisu: [reszta ogona A] [dissolve A->B] [cialo B] ... [ogon ostatniego]."""
    os.makedirs(out_dir, exist_ok=True)
    keep = max(fade, match_window, 1)
    ramp_match = cosine_ramp(match_window)
    report = {"joins": [], "frames_written": 0, "fade": fade, "match_window": match_window, "keep": keep}
    out_index = 0

    def write(rgb):
        nonlocal out_index
        out_index += 1
        save_frame(rgb, os.path.join(out_dir, f"frame_{out_index:06d}.png"))

    tail = []  # ostatnie `keep` klatek poprzedniego ujecia (surowe RGB float)

    for k, folder in enumerate(shot_dirs):
        files = list_frames(folder)
        n = len(files)
        if n < keep + fade + 1:
            sys.exit(f"Ujecie {folder} ma {n} klatek; potrzeba co najmniej {keep + fade + 1}")

        shot_sigma = 0.0
        if k == 0:
            body_start = 0
        else:
            head = [load_frame(f) for f in files[:keep]]
            head_raw = head  # metryka "przed" zawsze na surowych klatkach
            # rozmycie calego ujecia, gdy nowe ujecie jest ostrzejsze (P4, tryb blur_match)
            shot_sigma = 0.0
            sharp_before = top_band_lapvar(head[0], band)
            tail_ref = top_band_lapvar(tail[-1], band)
            if blur_match and sharp_before > tail_ref * 1.05:
                shot_sigma, _ = find_blur_sigma(head[0], tail_ref, band)
                head = [gaussian_blur(f, shot_sigma) for f in head]
            # statystyki Lab: A = ogon poprzedniego ujecia, B = poczatek biezacego
            # statystyki z 3 klatek przy samym szwie: srednia z dluzszego okna miesza dryf ujecia
            # i daje skok na pojedynczej klatce (sprawdzone w test_stitch.py)
            sn = min(3, keep)
            mu_a, sd_a = lab_stats([srgb_to_lab(f) for f in tail[-sn:]])
            mu_b, sd_b = lab_stats([srgb_to_lab(f) for f in head[:sn]])
            metrics_before = join_metrics(tail, head_raw, band)

            # ostrzenie, gdy nowe ujecie jest miensze (stosunek ostrosci head/tail < 1)
            ratio = metrics_before["sharp_ratio_head_over_tail"]
            sharp_amt = float(np.clip(1.0 / max(ratio, 1e-3) - 1.0, 0.0, 0.6)) if (sharpen and ratio < 0.95) else 0.0

            def corr_b(rgb, i):
                w = float(ramp_match[i]) if i < match_window else 0.0
                img = color_correct(rgb, mu_a, sd_a, mu_b, sd_b, w) if w > 0 else rgb
                return unsharp(img, sharp_amt * w) if w > 0 else img

            # 1) reszta ogona A, ktora nie wchodzi w dissolve (nieskorygowana)
            for i in range(keep - fade):
                write(tail[i])
            # 2) dissolve: alpha rosnie od 0 (widac A) do 1 (widac B), cosinusowo
            corrected_head = [corr_b(head[i], i) for i in range(fade)]
            for i in range(fade):
                alpha = 0.5 * (1 - np.cos(np.pi * (i + 1) / (fade + 1)))
                write(tail[keep - fade + i] * (1 - alpha) + corrected_head[i] * alpha)

            after = join_metrics([tail[-1]], [corrected_head[0]], band)
            report["joins"].append({"shot": k, "before": metrics_before, "after": after,
                                    "sharpen_amount": round(sharp_amt, 3),
                                    "blur_sigma_whole_shot": round(shot_sigma, 3),
                                    "lapvar_tail_ref": round(tail_ref, 6),
                                    "lapvar_head_before": round(sharp_before, 6)})
            body_start = fade

        # 3) cialo ujecia: bez ostatnich `keep` klatek (zostana na nastepny szew)
        for idx in range(body_start, n - keep):
            img = load_frame(files[idx])
            if k > 0 and shot_sigma > 0:
                img = gaussian_blur(img, shot_sigma)
            if k > 0 and idx < match_window:
                w = float(ramp_match[idx])
                if w > 0:
                    img = unsharp(color_correct(img, mu_a, sd_a, mu_b, sd_b, w), sharp_amt * w)
            write(img)

        tail = [load_frame(f) for f in files[n - keep:]]
        if k > 0 and shot_sigma > 0:
            tail = [gaussian_blur(f, shot_sigma) for f in tail]
        shot_sigma = 0.0  # dla ujecia k+1 wyznaczana od nowa


    # 4) ogon ostatniego ujecia
    for img in tail:
        write(img)

    report["frames_written"] = out_index
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return out_index, report


def deflicker(out_dir, window):
    """Wygladza srednia jasnosc L wzdluz calego ciagu (ruchoma srednia), usuwa blyski jasnosci."""
    files = sorted(glob.glob(os.path.join(out_dir, "frame_*.png")))
    means = []
    for f in files:
        means.append(float(srgb_to_lab(load_frame(f))[..., 0].mean()))
    means = np.array(means, dtype=np.float32)
    k = max(1, window)
    kernel = np.ones(k, dtype=np.float32) / k
    pad = k // 2
    padded = np.pad(means, (pad, pad), mode="edge")
    smooth = np.convolve(padded, kernel, mode="valid")[: len(means)]
    for f, m, s in zip(files, means, smooth):
        if m <= 0:
            continue
        lab = srgb_to_lab(load_frame(f))
        lab[..., 0] = np.clip(lab[..., 0] * (s / m), 0, 100)
        save_frame(lab_to_srgb(lab), f)
    return {"deflicker_window": k, "mean_L_before_max_step": round(float(np.abs(np.diff(means)).max()), 3),
            "mean_L_after_max_step": round(float(np.abs(np.diff(smooth)).max()), 3)}


def encode(out_dir, mp4, fps):
    """Kodowanie z jawnym BT.709 (tagi i konwersja RGB->YUV zgodna z BT.709)."""
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps), "-i", os.path.join(out_dir, "frame_%06d.png"),
        "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p",
        "-c:v", "libx264", "-crf", "14", "-preset", "slow",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", mp4,
    ]
    subprocess.run(cmd, check=True)
    return mp4


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_dir", help="folder na wyjsciowe klatki PNG")
    p.add_argument("shots", nargs="+", help="foldery ujec z klatkami PNG, w kolejnosci")
    p.add_argument("--fade", type=int, default=12, help="dlugosc dissolve na szwie w klatkach (domyslnie 12)")
    p.add_argument("--match-window", type=int, default=24, help="ile klatek korygowac kolor po szwie (domyslnie 24)")
    p.add_argument("--band", type=float, default=0.15, help="gorny pas kadru do pomiaru ostrosci (domyslnie 0.15)")
    p.add_argument("--sharpen", action="store_true", help="wyostrz nowe ujecie, gdy jest miensze od poprzedniego")
    p.add_argument("--deflicker", type=int, default=0, help="okno wygladzania jasnosci po calym ciagu (0 = wylaczone)")
    p.add_argument("--blur-match", action="store_true",
                   help="gdy nowe ujecie jest ostrzejsze, rozmyj CALE ujecie (jedna sigma, binarny podzial)")
    p.add_argument("--encode", metavar="MP4", help="zakoduj wynik do MP4 (BT.709)")
    p.add_argument("--fps", type=int, default=24)
    args = p.parse_args()

    report_path = os.path.join(args.out_dir, "stitch_report.json")
    os.makedirs(args.out_dir, exist_ok=True)
    n, report = stitch(args.shots, args.out_dir, args.fade, args.match_window, args.band,
                       args.sharpen, report_path, blur_match=args.blur_match)
    if args.deflicker:
        report["deflicker"] = deflicker(args.out_dir, args.deflicker)
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"zapisano {n} klatek w {args.out_dir}; raport: {report_path}")
    if args.encode:
        encode(args.out_dir, args.encode, args.fps)
        print(f"zakodowano: {args.encode}")


if __name__ == "__main__":
    main()
