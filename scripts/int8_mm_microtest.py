#!/usr/bin/env python3
"""Mikrotest int8 matmul na GPU (ROCm) przeciw CPU int32. Uruchamiaj w OSOBNYM procesie.

Cel: sprawdzic, czy torch._int_mm dziala na tej karcie i wersji ROCm. To NIE dowodzi, ze caly
potok kwantyzacji H3 dziala. Nie opieraj sie na gfx1100 (ComfyUI#15314) ani na patchu Windows.

Raportuje: wersje torch/HIP, nazwe urzadzenia, kształty, wynik porownania lub dokladny wyjatek.
Jesli torch nie jest zainstalowany albo nie ma GPU, zapisuje status BLOCKED i konczy z kodem 2.

Uzycie:  python3 scripts/int8_mm_microtest.py --out int8_microtest.json
"""
import argparse
import json
import sys
import traceback

SHAPES = [(16, 32, 16), (64, 64, 64), (33, 47, 19), (256, 512, 128)]  # ostatnie: niepodzielne przez 64


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="int8_microtest.json")
    args = ap.parse_args()
    rep = {"status": None, "torch": None, "hip": None, "device": None, "cases": [], "error": None}
    try:
        import torch
    except Exception as exc:  # brak torcha w tym srodowisku
        rep["status"] = "BLOCKED"
        rep["error"] = f"brak torch: {type(exc).__name__}: {exc}"
        return finish(rep, args.out, 2)

    rep["torch"] = torch.__version__
    rep["hip"] = getattr(torch.version, "hip", None)
    if not torch.cuda.is_available():  # ROCm uzywa API cuda
        rep["status"] = "BLOCKED"
        rep["error"] = "brak dostepnego GPU (torch.cuda.is_available() == False)"
        return finish(rep, args.out, 2)
    rep["device"] = torch.cuda.get_device_name(0)
    if not hasattr(torch, "_int_mm"):
        rep["status"] = "FAIL"
        rep["error"] = "torch._int_mm nie istnieje w tej wersji torch"
        return finish(rep, args.out, 1)

    gen = torch.Generator().manual_seed(0)
    all_ok = True
    for (m, k, n) in SHAPES:
        case = {"shape": [m, k, n]}
        try:
            a = torch.randint(-128, 127, (m, k), dtype=torch.int8, generator=gen)
            b = torch.randint(-128, 127, (k, n), dtype=torch.int8, generator=gen)
            # torch._int_mm wymaga, by pierwszy wymiar byl > 16 na czesci backendow: wynik i tak porownujemy
            gpu = torch._int_mm(a.cuda(), b.cuda()).cpu()
            cpu = (a.to(torch.int32) @ b.to(torch.int32))
            case["max_abs_diff"] = int((gpu.to(torch.int32) - cpu).abs().max())
            case["match"] = case["max_abs_diff"] == 0
        except Exception as exc:
            case["match"] = False
            case["exception"] = f"{type(exc).__name__}: {exc}"
            case["trace_tail"] = traceback.format_exc().splitlines()[-3:]
        all_ok &= case["match"]
        rep["cases"].append(case)
    rep["status"] = "PASS" if all_ok else "FAIL"
    return finish(rep, args.out, 0 if all_ok else 1)


def finish(rep, out, code):
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    print(json.dumps({k: rep[k] for k in ("status", "torch", "hip", "device", "error")}, ensure_ascii=False))
    print("raport:", out)
    return code


if __name__ == "__main__":
    sys.exit(main())
