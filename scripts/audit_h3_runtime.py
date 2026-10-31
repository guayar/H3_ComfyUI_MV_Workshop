#!/usr/bin/env python3
"""Audyt runtime ComfyUI pod workflow H3 (tylko odczyt, bez instalacji i pobierania).

Pyta lokalny serwer o schemat wezlow (GET /object_info) i stan systemu (GET /system_stats),
a potem zapisuje raport JSON i krotkie podsumowanie.

Statusy:
  OK                   - wszystkie wymagane wezly sa, a wymagane pliki widoczne w listach wyboru
  MODEL_NOT_INSTALLED  - wezel jest, ale oczekiwany plik nie figuruje w jego liscie wyboru
  NODE_MISSING         - brakuje wymaganego wezla (np. custom node nie jest zainstalowany)
  SERVER_UNREACHABLE   - serwer nie odpowiada; raport zawiera tylko liste wymagan, bez zgadywania

Uzycie:
  python3 scripts/audit_h3_runtime.py --url http://127.0.0.1:8188 --out h3_runtime_audit.json

Kazdy wpis ma etykiete zrodla: [CODE] = schemat z serwera, [MANIFEST] = oczekiwany plik z repo.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

# Wezly wymagane przez graf Ref2VA (potwierdzone w kodzie ComfyUI / szablonie).
REQUIRED_NODES = [
    "UNETLoader", "CLIPLoader", "VAELoader", "LoadImage", "MiniMaxH3ReferenceToVideo",
    "BasicScheduler", "KSamplerSelect", "RandomNoise", "BasicGuider", "SamplerCustomAdvanced",
    "VAEDecode", "ImageFromBatch", "SaveImage",
]
# Wezly potrzebne tylko dla wariantu ControlNet.
CONTROLNET_NODES = ["ModelPatchLoader", "MiniMaxH3FunControlNetApply", "LoadVideo", "GetVideoComponents"]
# Opcjonalne (eksperymenty, nie sa wymagane).
OPTIONAL_NODES = ["MiniMaxH3Extender", "MMH3HybridWindowSampler", "H3HybridWindows", "H3HybridControlNet",
                  "MiniMaxH3AddGuide"]

# Oczekiwane pliki [MANIFEST]: (wezel, wejscie, nazwa pliku). Nazwy pochodza z szablonu lub z listy
# oficjalnych plikow; kazda z nich musi figurowac w liscie wyboru serwera.
EXPECTED_FILES = [
    ("UNETLoader", "unet_name", "minimax_h3_ref2va_pruned_int8_convrot.safetensors"),
    ("CLIPLoader", "clip_name", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"),
    ("VAELoader", "vae_name", "minimax_h3_video_vae_int8_convrot.safetensors"),
    ("VAELoader", "vae_name", "minimax_h3_audio_vae_fp32.safetensors"),
    ("ModelPatchLoader", "name", "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"),
]
CONTROLNET_FILE_CANDIDATES = [
    "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors",
    "minimax_h3_fun_controlnet_union_pruned_bf16.safetensors",
    "minimax_h3_fun_controlnet_union_2.0_pruned_int8_convrot.safetensors",
    "minimax_h3_fun_controlnet_union_2.0_pruned_bf16.safetensors",
]


def fetch_json(url, timeout=8):
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def input_summary(schema):
    """Zwraca {name: {"required": bool, "type": str, "options": list|None}} z wejsc wezla."""
    out = {}
    for section, required in (("required", True), ("optional", False)):
        for name, spec in (schema.get("input", {}).get(section, {}) or {}).items():
            typ = spec[0] if isinstance(spec, list) and spec else spec
            options = None
            if isinstance(typ, list):  # lista wyboru (combo)
                options = typ
                typ = "COMBO"
            out[name] = {"required": required, "type": typ if isinstance(typ, str) else str(typ),
                         "options": options}
    return out


def output_summary(schema):
    names = schema.get("output_name") or schema.get("output") or []
    types = schema.get("output") or []
    return [{"name": n, "type": t} for n, t in zip(names, types)] or [{"name": t, "type": t} for t in types]


def audit(url):
    report = {"url": url, "status": "OK", "source": "[CODE] /object_info (serwer)",
              "system": {}, "nodes": {}, "files": [], "unmet": [], "notes": []}

    try:
        sysstats = fetch_json(f"{url}/system_stats")
        report["system"] = {
            "comfyui_version": sysstats.get("system", {}).get("comfyui_version"),
            "python_version": sysstats.get("system", {}).get("python_version"),
            "pytorch_version": sysstats.get("system", {}).get("pytorch_version"),
            "devices": [{"name": d.get("name"), "type": d.get("type"), "vram_total": d.get("vram_total")}
                        for d in sysstats.get("devices", [])],
        }
    except (urllib.error.URLError, OSError, ValueError) as exc:
        report["status"] = "SERVER_UNREACHABLE"
        report["notes"].append(f"serwer nie odpowiada ({type(exc).__name__}: {exc})")
        report["unmet"].append({"requirement": f"uruchom ComfyUI na {url}",
                                "action": "start ComfyUI (np. python main.py --listen 127.0.0.1 --port 8188) i uruchom audyt ponownie"})
        report["requirements_checklist"] = (REQUIRED_NODES + CONTROLNET_NODES)
        return report

    all_nodes = REQUIRED_NODES + CONTROLNET_NODES + OPTIONAL_NODES
    schemas = {}
    for node in all_nodes:
        try:
            data = fetch_json(f"{url}/object_info/{node}")
            schema = data.get(node)
        except (urllib.error.URLError, OSError, ValueError):
            schema = None
        if schema:
            schemas[node] = schema
            report["nodes"][node] = {"present": True, "required_group": (
                "required" if node in REQUIRED_NODES else "controlnet" if node in CONTROLNET_NODES else "optional"),
                "inputs": input_summary(schema), "outputs": output_summary(schema)}
        else:
            report["nodes"][node] = {"present": False, "required_group": (
                "required" if node in REQUIRED_NODES else "controlnet" if node in CONTROLNET_NODES else "optional")}

    for node in REQUIRED_NODES + CONTROLNET_NODES:
        if not report["nodes"][node]["present"]:
            report["unmet"].append({"requirement": f"wezel {node}", "action": "zainstaluj wymagany custom node albo wybierz wersje ComfyUI z tym wezlem"})
            report["status"] = "NODE_MISSING"

    # Sprawdz oczekiwane pliki w listach wyboru.
    for node, inp, expected in EXPECTED_FILES:
        entry = {"node": node, "input": inp, "expected": expected, "source": "[MANIFEST]"}
        info = report["nodes"].get(node, {})
        if not info.get("present"):
            entry["status"] = "NODE_MISSING"
        else:
            options = (info["inputs"].get(inp) or {}).get("options") or []
            entry["available"] = expected in options
            entry["status"] = "OK" if expected in options else "MODEL_NOT_INSTALLED"
            entry["options_count"] = len(options)
            if entry["status"] == "MODEL_NOT_INSTALLED":
                report["unmet"].append({"requirement": f"plik {expected} w {node}.{inp}",
                                        "action": "umiesc plik w odpowiednim folderze models/ i uruchom ComfyUI ponownie; nie podstawiaj innej nazwy"})
                if report["status"] == "OK":
                    report["status"] = "MODEL_NOT_INSTALLED"
        report["files"].append(entry)

    # ControlNet: ktory z oficjalnych kandydatow jest dostepny.
    mp = report["nodes"].get("ModelPatchLoader", {})
    if mp.get("present"):
        available = (mp["inputs"].get("name") or {}).get("options") or []
        report["controlnet_candidates"] = [{"file": c, "available": c in available} for c in CONTROLNET_FILE_CANDIDATES]
        report["notes"].append("ModelPatchLoader.name: wybierz plik z available=true; nie zgaduj nazwy")

    for node in OPTIONAL_NODES:
        if not report["nodes"][node]["present"]:
            report["notes"].append(f"opcjonalny wezel {node} nie jest zainstalowany (eksperyment pominiety)")
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--out", default="h3_runtime_audit.json")
    args = ap.parse_args()
    report = audit(args.url.rstrip("/"))
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f"status: {report['status']}")
    print(f"raport: {args.out}")
    for item in report["unmet"]:
        print(f"  BRAK: {item['requirement']} -> {item['action']}")
    return 0 if report["status"] == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
