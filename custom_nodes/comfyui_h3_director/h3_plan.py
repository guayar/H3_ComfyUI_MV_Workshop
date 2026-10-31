"""Logika planu H3 Director (bez zaleznosci od ComfyUI, torch i przegladarki).

Odpowiednik web/plan_core.js. Te same reguly, te same wartosci graniczne:
  * limity referencji H3 [CODE nodes_minimax_h3.py]: 9 obrazow, 3 wideo, 3 audio
  * obraz ostatniej klatki poprzedniego ujecia zajmuje jeden slot obrazu (przy >1 ujeciu limit to 8)
  * dlugosc klatek w siatce 17n+5 przy 24 fps
  * jedna generacja: najwyzej 14,4 s

Ten modul nie czyta plikow ani nie laduje obrazow. To robi h3_director_node.py.
"""
import re

FPS = 24
REF_LIMITS = {"images": 9, "videos": 3, "audio": 3}
EXT = {
    "images": (".png", ".jpg", ".jpeg", ".webp"),
    "videos": (".mp4", ".webm", ".mov", ".mkv"),
    "audio": (".wav", ".mp3", ".flac", ".ogg"),
}
SAFE_NAME = re.compile(r"^[A-Za-z0-9_\-. ]+$")
MAX_SHOT_SECONDS = 14.4
TIME_PART = re.compile(r"^\d+(\.\d+)?$")


class PlanError(ValueError):
    """Blad planu zrozumialy dla uzytkownika (ten sam komunikat co w panelu)."""


def parse_time(value):
    """Akceptuje liczbe (sekundy) albo tekst: '12.5', '1:02.5', '0:01:02.5'."""
    if isinstance(value, bool):
        raise PlanError("czas musi byc liczba lub tekstem")
    if isinstance(value, (int, float)):
        if value < 0:
            raise PlanError("czas musi byc liczba >= 0")
        return float(value)
    text = str(value).strip()
    if not text:
        raise PlanError("pusty czas")
    parts = text.split(":")
    if len(parts) > 3:
        raise PlanError(f"zly format czasu: {text}")
    nums = [p.strip() for p in parts]
    if not all(TIME_PART.match(p) for p in nums):
        raise PlanError(f"zly format czasu: {text}")
    values = [float(p) for p in nums]
    for v in values[:-1]:
        if not v.is_integer():
            raise PlanError(f"zly format czasu: {text}")
    if len(values) > 1:
        if values[-1] >= 60:
            raise PlanError(f"sekundy >= 60 w: {text}")
        if len(values) == 3 and values[1] >= 60:
            raise PlanError(f"minuty >= 60 w: {text}")
    total = 0.0
    for v in values:
        total = total * 60 + v
    return total


def format_time(seconds):
    sign = "-" if seconds < 0 else ""
    sec = abs(seconds)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec - h * 3600 - m * 60
    body = f"{h}:{m:02d}:{s:05.2f}" if h > 0 else f"{m}:{s:05.2f}"
    return sign + body


def snap_frames(seconds, fps=FPS):
    """Najblizsza liczba klatek w siatce 17n+5 (min 5)."""
    raw = seconds * fps
    n = max(0, round((raw - 5) / 17))
    return 17 * n + 5


def shot_frames(shot):
    return snap_frames(shot["end"] - shot["start"], FPS)


def validate_shots(shots):
    """Zwraca (bledy, ostrzezenia). Logika zgodna z plan_core.js."""
    errors, warnings = [], []
    ordered = sorted(shots, key=lambda s: s["start"])
    for i, s in enumerate(ordered):
        if not s["end"] > s["start"]:
            errors.append(f"ujecie {i + 1}: koniec musi byc po poczatku")
        if not str(s.get("prompt") or "").strip():
            warnings.append(f"ujecie {i + 1}: pusty prompt")
        if i > 0:
            prev = ordered[i - 1]
            if s["start"] < prev["end"] - 1e-9:
                errors.append(f"ujecia {i} i {i + 1} nachodza sie")
            elif s["start"] > prev["end"] + 1e-9:
                warnings.append(f"przerwa miedzy ujeciami {i} i {i + 1}")
        dur = s["end"] - s["start"]
        if 0 < dur < 2:
            warnings.append(f"ujecie {i + 1} krotsze niz 2 s")
        if dur > MAX_SHOT_SECONDS:
            errors.append(f"ujecie {i + 1} dluzsze niz 14,4 s (limit jednej generacji)")
    return errors, warnings


def image_limit(shot_count):
    return REF_LIMITS["images"] - 1 if shot_count > 1 else REF_LIMITS["images"]


def validate_refs(refs, shot_count):
    errors = []
    limits = {"images": image_limit(shot_count), "videos": REF_LIMITS["videos"], "audio": REF_LIMITS["audio"]}
    for kind, lim in limits.items():
        used = len(refs.get(kind, []))
        if used > lim:
            errors.append(f"za duzo referencji {kind}: {used} > {lim}")
    if refs.get("audio") and not refs.get("images") and not refs.get("videos"):
        errors.append("audio wymaga co najmniej jednej referencji obrazu lub wideo")
    for kind, names in refs.items():
        for name in names:
            if not SAFE_NAME.match(name):
                errors.append(f"nazwa pliku {name!r}: dozwolone litery, cyfry, _ - . i spacje")
            elif not name.lower().endswith(EXT.get(kind, ())):
                errors.append(f"zle rozszerzenie dla {kind}: {name}")
    return errors


def load_plan(data):
    """Waliduje slownik planu (wynik eksportu z panelu). Zwraca znormalizowany slownik albo rzuca PlanError."""
    if not isinstance(data, dict) or data.get("version") != 1:
        raise PlanError("to nie jest plan H3 Director (version 1)")
    shots_in = data.get("shots")
    if not isinstance(shots_in, list) or not shots_in:
        raise PlanError("plan nie zawiera ujec")
    shots = []
    for k, sp in enumerate(shots_in):
        try:
            start = float(sp["start"])
            end = float(sp["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise PlanError(f"ujecie {k + 1}: brak poprawnego start/end") from exc
        frames = int(sp.get("frames", snap_frames(end - start)))
        if frames % 17 != 5:
            raise PlanError(f"ujecie {k + 1} ma {frames} klatek (nie 17n+5)")
        shots.append({"start": start, "end": end, "frames": frames, "prompt": str(sp.get("prompt") or "")})
    refs_in = data.get("refs") or {}
    refs = {kind: [str(x) for x in refs_in.get(kind, [])] for kind in ("images", "videos", "audio")}
    errors, _ = validate_shots(shots)
    errors += validate_refs(refs, len(shots))
    if errors:
        raise PlanError("; ".join(errors))
    return {"version": 1, "fps": FPS, "shots": shots, "refs": refs}


def output_slots(plan):
    """Przypisuje referencje do stalych slotow wyjsc wezla.

    Zwraca slownik: images[0..8], videos[0..2], audio[0..2] -> nazwa pliku albo None (slot pusty).
    Aktywne sa tylko pierwsze N pozycji kazdego rodzaju (progresja, bez dziur).
    """
    refs = plan["refs"]
    images = [None] * REF_LIMITS["images"]
    for k, name in enumerate(refs["images"]):
        images[k] = name
    videos = [None] * REF_LIMITS["videos"]
    for k, name in enumerate(refs["videos"]):
        videos[k] = name
    audio = [None] * REF_LIMITS["audio"]
    for k, name in enumerate(refs["audio"]):
        audio[k] = name
    return {"images": images, "videos": videos, "audio": audio}
