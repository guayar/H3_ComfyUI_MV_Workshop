#!/usr/bin/env python3
"""Testy logiki planu (h3_plan.py). Te same przypadki co tests/test_plan_core.js.

Uruchomienie: python3 custom_nodes/comfyui_h3_director/tests/test_h3_plan.py
"""
import json
import os
import sys

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PKG)
import h3_plan as P  # noqa: E402


def raises(fn, pattern):
    try:
        fn()
    except P.PlanError as exc:
        import re
        assert re.search(pattern, str(exc)), str(exc)
        return
    raise AssertionError("oczekiwano PlanError")


def main():
    # 1. czas
    assert P.parse_time("12.5") == 12.5
    assert P.parse_time("1:02.5") == 62.5
    assert P.parse_time("0:01:02.5") == 62.5
    raises(lambda: P.parse_time("1:75"), "sekundy >= 60")
    raises(lambda: P.parse_time("abc"), "zly format")
    raises(lambda: P.parse_time(-3), ">= 0")
    assert P.format_time(62.5) == "1:02.50"
    print("OK 1: parsowanie i formatowanie czasu jak w panelu")

    # 2. klatki 17n+5 (te same wartosci co w JS)
    assert P.snap_frames(5.17) == 124
    assert P.snap_frames(10.125) == 243
    assert P.snap_frames(4) == 90
    for k in range(1, 300):
        s = k * 0.047
        assert (P.snap_frames(s) - 5) % 17 == 0
    print("OK 2: wszystkie dlugosci w siatce 17n+5")

    # 3. walidacja ujec
    e, _ = P.validate_shots([{"start": 0, "end": 10, "prompt": "a"}, {"start": 9, "end": 20, "prompt": "b"}])
    assert any("nachodza" in x for x in e)
    e, _ = P.validate_shots([{"start": 0, "end": 20, "prompt": "a"}])
    assert any("14,4" in x for x in e)
    _, w = P.validate_shots([{"start": 0, "end": 5, "prompt": ""}])
    assert any("pusty prompt" in x for x in w)
    print("OK 3: nakladanie, zbyt dlugie ujecie, pusty prompt")

    # 4. limity referencji
    assert P.image_limit(3) == 8 and P.image_limit(1) == 9
    refs = {"images": [f"i{k}.png" for k in range(9)], "videos": [], "audio": []}
    assert P.validate_refs(refs, 3)  # 9 > 8 przy wielu ujeciach
    assert not P.validate_refs(refs, 1)
    assert P.validate_refs({"images": [], "videos": [], "audio": ["a.wav"]}, 1)
    assert P.validate_refs({"images": ["../x.png"], "videos": [], "audio": []}, 1)
    assert P.validate_refs({"images": ["kot.mp4"], "videos": [], "audio": []}, 1)
    print("OK 4: limity obrazow (8/9), wideo, audio, nazwy i rozszerzenia")

    # 5. wczytanie planu z panelu i progresja slotow
    plan_data = {"version": 1, "fps": 24, "duration": 60, "shots": [
        {"start": 0.0, "end": 5.17, "frames": 124, "prompt": "walks in"},
        {"start": 5.17, "end": 15.3, "frames": 243, "prompt": "turns"}],
        "refs": {"images": ["set_plate.png", "character_sheet.png"], "videos": [], "audio": []}}
    plan = P.load_plan(plan_data)
    slots = P.output_slots(plan)
    assert slots["images"][:2] == ["set_plate.png", "character_sheet.png"]
    assert all(x is None for x in slots["images"][2:]), "puste sloty powinny byc None (bez dziur)"
    assert slots["videos"] == [None, None, None]
    print("OK 5: plan wczytany, aktywne sloty z przodu, reszta None")

    # 6. zly plan jest odrzucany
    bad = json.loads(json.dumps(plan_data))
    bad["shots"][0]["frames"] = 120
    raises(lambda: P.load_plan(bad), "17n\\+5|nie 17n")
    raises(lambda: P.load_plan({"version": 2, "shots": []}), "version 1")
    print("OK 6: zly plan (klatki, wersja) odrzucany")

    print("\nWszystkie testy h3_plan OK.")


if __name__ == "__main__":
    main()
