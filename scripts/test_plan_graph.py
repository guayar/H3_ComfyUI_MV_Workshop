#!/usr/bin/env python3
"""Test: plan z panelu H3 Director -> graf UI (ujecia, dlugosci, prompty, pliki referencji).

Uzywa planu w formacie planToJSON (version 1). Walidacja na fiksturze schematu.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_ui_chain as b  # noqa: E402
import test_validate_graph_offline as tv  # noqa: E402
import validate_graph_offline as v  # noqa: E402

PLAN = {
    "version": 1, "fps": 24, "duration": 248.76,
    "shots": [
        {"start": 0.0, "end": 5.17, "frames": 124, "prompt": "The gardener walks in, camera locked off."},
        {"start": 5.17, "end": 15.3, "frames": 243, "prompt": "He turns toward the roses and grabs his head."},
        {"start": 15.3, "end": 22.0, "frames": 158, "prompt": "Roses stare at him, locked tripod."},
    ],
    "refs": {"images": ["hall_plate.png", "gardener_sheet.png", "rose_close.png"],
             "videos": ["ref_video_01.mp4"], "audio": ["ref_audio_01.wav"]},
}


def main():
    g = b.build(0, 0, plan=PLAN)
    shots = [n for n in g["nodes"] if n["type"] == "MiniMaxH3ReferenceToVideo"]
    assert len(shots) == 3, len(shots)
    assert [n["widgets_values"][3] for n in shots] == [124, 243, 158]
    assert [n["widgets_values"][0] for n in shots][0].startswith("The gardener walks in")
    names = {n["type"]: [] for n in g["nodes"]}
    loads = [n["widgets_values"][0] for n in g["nodes"] if n["type"] == "LoadImage"]
    assert loads[:3] == ["hall_plate.png", "gardener_sheet.png", "rose_close.png"], loads
    assert "ref_video_01.mp4" in [n["widgets_values"][0] for n in g["nodes"] if n["type"] == "LoadVideo"]
    assert "ref_audio_01.wav" in [n["widgets_values"][0] for n in g["nodes"] if n["type"] == "LoadAudio"]
    print("OK 1: ujecia 3, dlugosci 124/243/158, prompty, pliki referencji z planu")

    sch = tv.fixture(image_files=("hall_plate.png", "gardener_sheet.png", "rose_close.png"),
                     video_files=("ref_video_01.mp4", "control_shot_01.mp4"))
    sch["MarkdownNote"] = {"input": {"required": {"text": ["STRING", {"multiline": True}]}}, "output": []}
    sch["LoadAudio"] = {"input": {"required": {"audio": [["ref_audio_01.wav"], {"audio_upload": True}]}},
                        "output": ["AUDIO"]}
    e, _ = v.validate_ui(g, sch)
    assert not e, [x["code"] + " " + x["where"] for x in e][:5]
    print("OK 2: graf z planu przechodzi walidacje na fiksturze")

    # ostatnia klatka poprzedniego ujecia: indeks = klatki_poprzedniego - 1
    prev_nodes = [n for n in g["nodes"] if n["type"] == "ImageFromBatch"]
    assert [n["widgets_values"][0] for n in prev_nodes] == [123, 242], [n["widgets_values"] for n in prev_nodes]
    print("OK 3: ostatnia klatka kazdego ujecia liczona z jego dlugosci")

    # CLI: zly plan (klatki nie 17n+5) jest odrzucany
    bad = json.loads(json.dumps(PLAN))
    bad["shots"][0]["frames"] = 120
    with tempfile.TemporaryDirectory() as tmp:
        pth = os.path.join(tmp, "plan.json")
        json.dump(bad, open(pth, "w"))
        res = subprocess.run([sys.executable, os.path.join(HERE, "build_ui_chain.py"), "--plan", pth,
                              "--out", os.path.join(tmp, "g.json")], capture_output=True, text=True)
        assert res.returncode == 2 and "17n+5" in res.stderr, (res.returncode, res.stderr)
        # CLI: poprawny plan zapisuje graf
        ok = os.path.join(tmp, "plan_ok.json")
        json.dump(PLAN, open(ok, "w"))
        out = os.path.join(tmp, "g2.json")
        res = subprocess.run([sys.executable, os.path.join(HERE, "build_ui_chain.py"), "--plan", ok, "--out", out],
                             capture_output=True, text=True)
        assert res.returncode == 0, res.stderr
        assert len(json.load(open(out))["nodes"]) > 10
    print("OK 4: CLI odrzuca zla klatke, przyjmuje poprawny plan")
    print("\nWszystkie testy planu OK.")


if __name__ == "__main__":
    main()
