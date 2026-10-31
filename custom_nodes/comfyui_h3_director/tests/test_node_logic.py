#!/usr/bin/env python3
"""Testy wezla H3Director bez ComfyUI: mapowanie wyjsc, wczytywanie pakietu, bledy wejscia.

Uruchomienie: python3 custom_nodes/comfyui_h3_director/tests/test_node_logic.py
"""
import importlib.util
import json
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PKG)
import h3_director_node as N  # noqa: E402


def sample_plan(images):
    return json.dumps({"version": 1, "fps": 24, "duration": 60, "shots": [
        {"start": 0.0, "end": 5.17, "frames": 124, "prompt": "The gardener walks in."},
        {"start": 5.17, "end": 15.3, "frames": 243, "prompt": "He turns toward the roses."}],
        "refs": {"images": images, "videos": ["ref_video_01.mp4"], "audio": ["ref_audio_01.wav"]}})


def main():
    # 1. pakiet laduje sie z relatywnymi importami i ma rejestracje
    spec = importlib.util.spec_from_file_location(
        "comfyui_h3_director", os.path.join(PKG, "__init__.py"),
        submodule_search_locations=[PKG])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["comfyui_h3_director"] = mod  # relatywne importy wymagaja zarejestrowanego pakietu
    spec.loader.exec_module(mod)
    cls = mod.NODE_CLASS_MAPPINGS["H3Director"]  # ten sam kod, inny obiekt modulu (import pakietowy)
    assert cls.__name__ == "H3Director" and cls.FUNCTION == "run" and cls.CATEGORY == "H3/Director"
    assert mod.WEB_DIRECTORY == "./web"
    assert os.path.exists(os.path.join(PKG, "web", "h3_director.js"))
    assert os.path.exists(os.path.join(PKG, "web", "h3_director_panel.html"))
    print("OK 1: __init__ rejestruje H3Director, katalog web/ istnieje")

    # 2. schemat wezla: 9 slotow IMAGE + summary + shot_count
    types = N.H3Director.RETURN_TYPES
    assert types[:9] == ("IMAGE",) * 9, types
    assert types[9:] == ("STRING", "INT"), types
    assert len(N.H3Director.RETURN_NAMES) == len(types)
    assert N.H3Director.INPUT_TYPES()["required"]["plan_json"][0] == "STRING"
    print("OK 2: schemat wyjsc zgodny z limitem 9 obrazow")

    # 3. wykonanie: aktywne sloty maja nazwy, reszta None, licznik ujec
    images, summary, count = N.run_core(sample_plan(["set_plate.png", "character_sheet.png", "rose.png"]))
    assert count == 2
    assert images[:3] == ["set_plate.png", "character_sheet.png", "rose.png"]
    assert all(x is None for x in images[3:])
    assert "ref_video_01.mp4" in summary and "ref_audio_01.wav" in summary
    assert "124 kl." in summary and "243 kl." in summary
    print("OK 3: wyjscia: aktywne sloty z nazwami, reszta None, podsumowanie")

    # 4. loader wywolywany tylko dla aktywnych slotow
    calls = []
    images2, _, _ = N.run_core(sample_plan(["a.png", "b.png"]), loader=lambda n: calls.append(n) or f"T:{n}")
    assert calls == ["a.png", "b.png"], calls
    assert images2[:2] == ["T:a.png", "T:b.png"] and images2[2] is None
    print("OK 4: loader wywolany tylko dla uzywanych slotow")

    # 5. bledy wejscia maja czytelny komunikat
    for bad, pattern in [("", "pusty plan"), ("{nie json", "nie jest poprawnym JSON"),
                         ("{\"version\": 1, \"shots\": []}", "nie zawiera ujec")]:
        try:
            N.run_core(bad)
        except ValueError as exc:
            assert pattern in str(exc), str(exc)
        else:
            raise AssertionError(f"brak bledu dla {bad!r}")
    print("OK 5: puste wejscie, zly JSON i plan bez ujec daja czytelne bledy")

    # 6. maksymalnie 9 obrazow z limitem 8 przy wielu ujeciach (plan z panelu tego pilnuje)
    try:
        N.run_core(sample_plan([f"i{k}.png" for k in range(9)]))
    except ValueError as exc:
        assert "limit" in str(exc) or "za duzo" in str(exc), str(exc)
    else:
        raise AssertionError("9 obrazow przy 2 ujeciach powinno byc odrzucone")
    print("OK 6: 9 obrazow przy wielu ujeciach odrzucone (limit 8)")

    print("\nWszystkie testy wezla OK (bez ComfyUI; wczytywanie obrazow testowane w ComfyUI).")


if __name__ == "__main__":
    main()
