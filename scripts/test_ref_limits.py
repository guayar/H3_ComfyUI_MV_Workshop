#!/usr/bin/env python3
"""Testy limitow referencji H3 w generatorze grafu (9 obrazow, 3 wideo, 3 audio) [CODE nodes_minimax_h3.py].

Sprawdza: liczby wejsc referencji w kazdym ujeciu, odrzucenie przekroczenia, poprawnosc polaczen
(walidator na fiksturze), brak zmian w domyslnym grafie bez dodatkowych referencji.
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_ui_chain as b  # noqa: E402
import test_validate_graph_offline as tv  # noqa: E402
import validate_graph_offline as v  # noqa: E402


def counts(graph):
    out = []
    for n in graph["nodes"]:
        if n["type"] == "MiniMaxH3ReferenceToVideo":
            names = [i["name"] for i in n["inputs"]]
            out.append((sum(x.startswith("ref_image_") for x in names),
                        sum(x.startswith("ref_video_") for x in names),
                        sum(x.startswith("ref_audio_") for x in names)))
    return out


def main():
    full = b.build(3, 243, extra_images=6, ref_videos=3, ref_audios=3)
    c = counts(full)
    assert c[0] == (8, 3, 3), c[0]           # pierwsze ujecie: bez poprzedniej klatki
    assert all(x == (9, 3, 3) for x in c[1:]), c
    print("OK 1: 9 obrazow, 3 wideo, 3 audio w ujeciach 2-3 (pierwsze: 8 obrazow, bez poprzedniej klatki)")

    extra_imgs = ["set_plate.png", "character_sheet.png"] + [f"extra_ref_image_{k:02d}.png" for k in range(1, 7)]
    sch = tv.fixture(image_files=tuple(extra_imgs),
                     video_files=("control_shot_01.mp4", "control_shot_02.mp4", "control_shot_03.mp4",
                                  "ref_video_01.mp4", "ref_video_02.mp4", "ref_video_03.mp4"))
    sch["MarkdownNote"] = {"input": {"required": {"text": ["STRING", {"multiline": True}]}}, "output": []}
    sch["LoadAudio"] = {"input": {"required": {"audio": [[f"ref_audio_{k:02d}.wav" for k in range(1, 4)],
                                                        {"audio_upload": True}]}}, "output": ["AUDIO"]}
    e, _ = v.validate_ui(full, sch)
    assert not e, [x["code"] + " " + x["where"] for x in e][:5]
    print("OK 2: pelny graf z referencjami przechodzi walidacje na fiksturze")

    default = b.build(3, 243)
    assert counts(default)[0] == (2, 0, 0)
    assert counts(default)[1] == (3, 0, 0)
    print("OK 3: domyslny graf bez zmian (2 obrazy w ujeciu 1, 3 w pozostalych, bez wideo i audio)")

    # limit egzekwuje CLI: kod wyjscia 2 przy 7 dodatkowych obrazach przy 3 ujeciach
    here = os.path.dirname(os.path.abspath(__file__))
    res = subprocess.run([sys.executable, os.path.join(here, "build_ui_chain.py"), "--shots", "3",
                          "--extra-ref-images", "7", "--out", os.devnull], capture_output=True, text=True)
    assert res.returncode == 2 and "najwyzej 9" in res.stderr, (res.returncode, res.stderr)
    print("OK 4: CLI odrzuca 10. obraz referencji (limit 9)")
    print("\nWszystkie testy limitow referencji OK.")


if __name__ == "__main__":
    main()
