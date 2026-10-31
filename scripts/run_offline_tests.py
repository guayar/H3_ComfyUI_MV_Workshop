#!/usr/bin/env python3
"""Uruchamia wszystkie testy, ktore nie wymagaja ComfyUI, GPU ani sieci.

Uzycie:  python3 scripts/run_offline_tests.py [folder_roboczy]
Kod wyjscia 0 = wszystkie przeszly. Kazdy zestaw ma wlasny folder roboczy w podanym katalogu.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    "test_stitch.py",
    "test_sharpness_blur.py",
    "test_flap_mask.py",
    "test_measure_scene_drift.py",
    "test_homography_drift.py",
    "test_audit_h3_runtime.py",
    "test_validate_graph_offline.py",
    "test_ref_limits.py",
    "test_plan_graph.py",
    "../custom_nodes/comfyui_h3_director/tests/test_h3_plan.py",
    "../custom_nodes/comfyui_h3_director/tests/test_node_logic.py",
]


# Testy panelu w Node (bez przegladarki): logika planu. Test UI (Playwright) jest w custom_nodes/comfyui_h3_director/tests/test_panel_ui.js.
NODE_SUITES = ["custom_nodes/comfyui_h3_director/tests/test_plan_core.js"]


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="h3_offline_")
    os.makedirs(root, exist_ok=True)
    failed = []
    for name in SUITES:
        work = os.path.join(root, name.replace(".py", ""))
        res = subprocess.run([sys.executable, os.path.join(HERE, name), work],
                             capture_output=True, text=True, timeout=1800)
        status = "OK" if res.returncode == 0 else "FAIL"
        last = (res.stdout.strip().splitlines() or [""])[-1][:90]
        print(f"{status:4} {name:32} {last}")
        if res.returncode != 0:
            failed.append(name)
            print(res.stdout[-800:], res.stderr[-800:])
    here_root = os.path.dirname(HERE)
    for rel in NODE_SUITES:
        res = subprocess.run(["node", os.path.join(here_root, rel)], capture_output=True, text=True, timeout=600)
        status = "OK" if res.returncode == 0 else "FAIL"
        last = (res.stdout.strip().splitlines() or [""])[-1][:90]
        print(f"{status:4} {rel:32} {last}")
        if res.returncode != 0:
            failed.append(rel)
            print(res.stdout[-800:], res.stderr[-800:])
    total = len(SUITES) + len(NODE_SUITES)
    print(f"\n{total - len(failed)}/{total} zestawow OK. Folder: {root}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
