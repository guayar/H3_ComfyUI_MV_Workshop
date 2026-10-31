"""Wezel ComfyUI „H3 Director”: zamienia plan z panelu na 9 slotow obrazow referencji.

Wejscie: plan_json (tekst JSON zapisany przez panel H3 Director).
Wyjscia: ref_image_0 ... ref_image_8 (IMAGE; pusty slot = None), summary (STRING), shot_count (INT).

Wideo i audio NIE sa dekodowane w tym wezle. Podlacz je osobnymi wezlami core ComfyUI:
  LoadVideo -> GetVideoComponents (images) -> ref_video_N ; LoadAudio -> ref_audio_N.
Lista plikow wideo i audio jest w polu summary.

Zasada wiringu: podlacz tylko uzywane sloty (np. ref_image_0..k). Podlaczenie pustego slotu
da blad wykonania. [UNVERIFIED na Twoim ComfyUI: obsluga None na wyjsciu].
"""
import json

try:  # w ComfyUI pakiet jest importowany jako pakiet
    from . import h3_plan
except ImportError:  # w testach modul jest importowany bezposrednio
    import h3_plan

NUM_IMAGE_SLOTS = h3_plan.REF_LIMITS["images"]


def run_core(plan_json, loader=None):
    """Logika bez ComfyUI. loader(nazwa_pliku) -> obiekt obrazu (np. tensor); domyslnie zwraca nazwe.

    Zwraca (slots, summary, shot_count), gdzie slots to lista 9 elementow: loader(nazwa) albo None.
    """
    if not plan_json or not str(plan_json).strip():
        raise ValueError("H3 Director: pusty plan. Otworz panel i zapisz plan.")
    try:
        data = json.loads(plan_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"H3 Director: plan nie jest poprawnym JSON ({exc})") from exc
    plan = h3_plan.load_plan(data)
    slots = h3_plan.output_slots(plan)
    load = loader or (lambda name: name)
    images = [load(name) if name is not None else None for name in slots["images"]]
    summary_lines = [
        f"ujec: {len(plan['shots'])}",
        *[f"  {k + 1}: {s['start']:.2f}-{s['end']:.2f} s, {s['frames']} kl., {s['prompt'][:60]}"
          for k, s in enumerate(plan["shots"])],
        f"obrazy: {', '.join(n for n in plan['refs']['images']) or '-'}",
        f"wideo (podlacz LoadVideo+GetVideoComponents): {', '.join(plan['refs']['videos']) or '-'}",
        f"audio (podlacz LoadAudio): {', '.join(plan['refs']['audio']) or '-'}",
    ]
    return images, "\n".join(summary_lines), len(plan["shots"])


def load_image_tensor(filename):
    """Laduje plik z katalogu input/ ComfyUI jako tensor (1, H, W, 3) float32 0..1. Tylko w ComfyUI."""
    import numpy as np
    import torch
    from PIL import Image

    import folder_paths  # dostepne tylko w ComfyUI

    path = folder_paths.get_annotated_filepath(filename)
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None,]


class H3Director:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "plan_json": ("STRING", {"multiline": True, "default": "{}"}),
        }}

    RETURN_TYPES = tuple(["IMAGE"] * NUM_IMAGE_SLOTS + ["STRING", "INT"])
    RETURN_NAMES = tuple([f"ref_image_{k}" for k in range(NUM_IMAGE_SLOTS)] + ["summary", "shot_count"])
    FUNCTION = "run"
    CATEGORY = "H3/Director"
    DESCRIPTION = ("Plan ujec i referencji z panelu H3 Director. Kazdy slot ref_image_N to kolejna referencja "
                   "obrazu; podlacz tylko uzywane sloty.")

    def run(self, plan_json):
        images, summary, shot_count = run_core(plan_json, loader=load_image_tensor)
        return tuple(images + [summary, shot_count])
