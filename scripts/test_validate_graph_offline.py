#!/usr/bin/env python3
"""Testy walidatora offline na FIKSTURZE schematu (recznie spisanym, NIE z uruchomionego ComfyUI).

Fikstura odzwierciedla wejscia/wyjscia potwierdzone w kodzie i szablonach. Pliki w listach wyboru
sa jawnie wypisane. Te testy sprawdzaja logike walidatora, nie zgodnosc z Twoja instalacja.
Prawdziwa walidacja: scripts/audit_h3_runtime.py + validate_graph_offline.py z object_info.json.
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import validate_graph_offline as v  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNET = "minimax_h3_ref2va_pruned_int8_convrot.safetensors"
CLIP = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE_V = "minimax_h3_video_vae_int8_convrot.safetensors"
VAE_A = "minimax_h3_audio_vae_fp32.safetensors"
CN = "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"


def fixture(cn_options=(CN,), video_files=("control_shot_01.mp4", "control_shot_02.mp4", "control_shot_03.mp4"),
            image_files=("set_plate.png", "character_sheet.png")):
    def req(typ, **meta):
        return [typ, meta] if meta else [typ]
    return {
        "UNETLoader": {"input": {"required": {"unet_name": [[UNET]], "weight_dtype": [["default", "fp8_e4m3fn"]]}},
                       "output": ["MODEL"]},
        "CLIPLoader": {"input": {"required": {"clip_name": [[CLIP]], "type": [["minimax"]], "device": [["default"]]}},
                       "output": ["CLIP"]},
        "VAELoader": {"input": {"required": {"vae_name": [[VAE_V, VAE_A]]}}, "output": ["VAE"]},
        "LoadImage": {"input": {"required": {"image": [list(image_files), {"image_upload": True}]}},
                      "output": ["IMAGE", "MASK"]},
        "MiniMaxH3ReferenceToVideo": {"input": {"required": {
            "clip": ["CLIP"], "prompt": ["STRING", {"multiline": True}],
            "width": ["INT", {"min": 32, "max": 4096, "step": 32}],
            "height": ["INT", {"min": 32, "max": 4096, "step": 32}],
            "length": ["INT", {"min": 5, "max": 3600, "step": 17}],
            "ref_image_size": [["match", "max"]]},
            "optional": {"vae": ["VAE"], "audio_vae": ["VAE"]}},
            "output": ["CONDITIONING", "LATENT"], "output_name": ["positive", "LATENT"]},
        "BasicScheduler": {"input": {"required": {"model": ["MODEL"], "scheduler": [["simple", "normal"]],
                                                  "steps": ["INT", {"min": 1, "max": 10000}],
                                                  "denoise": ["FLOAT", {"min": 0.0, "max": 1.0}]}},
                           "output": ["SIGMAS"]},
        "KSamplerSelect": {"input": {"required": {"sampler_name": [["res_multistep", "euler"]]}},
                           "output": ["SAMPLER"]},
        "RandomNoise": {"input": {"required": {"noise_seed": ["INT", {"control_after_generate": True}]}},
                        "output": ["NOISE"]},
        "BasicGuider": {"input": {"required": {"model": ["MODEL"], "conditioning": ["CONDITIONING"]}},
                        "output": ["GUIDER"]},
        "SamplerCustomAdvanced": {"input": {"required": {"noise": ["NOISE"], "guider": ["GUIDER"],
                                                         "sampler": ["SAMPLER"], "sigmas": ["SIGMAS"],
                                                         "latent_image": ["LATENT"]}},
                                  "output": ["LATENT", "LATENT"], "output_name": ["output", "denoised_output"]},
        "VAEDecode": {"input": {"required": {"samples": ["LATENT"], "vae": ["VAE"]}}, "output": ["IMAGE"]},
        "ImageFromBatch": {"input": {"required": {"image": ["IMAGE"], "batch_index": ["INT", {}], "length": ["INT", {}]}},
                           "output": ["IMAGE"]},
        "SaveImage": {"input": {"required": {"images": ["IMAGE"], "filename_prefix": ["STRING", {}]}}, "output": []},
        "ModelPatchLoader": {"input": {"required": {"name": [list(cn_options)]}}, "output": ["MODEL_PATCH"]},
        "LoadVideo": {"input": {"required": {"file": [list(video_files), {"video_upload": True}]}}, "output": ["VIDEO"]},
        "GetVideoComponents": {"input": {"required": {"video": ["VIDEO"]}}, "output": ["IMAGE", "AUDIO", "FLOAT"]},
        "MiniMaxH3FunControlNetApply": {"input": {"required": {
            "model": ["MODEL"], "model_patch": ["MODEL_PATCH"], "vae": ["VAE"],
            "strength": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0}],
            "start_percent": ["FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0}],
            "end_percent": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0}]},
            "optional": {"control_video": ["IMAGE"], "mask": ["MASK"], "source_video": ["IMAGE"]}},
            "output": ["MODEL"]},
    }


def load(name):
    return json.load(open(os.path.join(ROOT, "workflows", name), encoding="utf-8"))


def codes(report):
    return [e["code"] for e in report[1]]


def run(graph, schema):
    return v.validate_ui(graph, schema)


def main():
    cn_graph = load("h3_chain_controlnet_ui.json")
    chain_graph = load("h3_chain_ui.json")
    api_graph = load("h3_r2v_shot_api.json")
    schema = fixture()

    # 1. oba grafy UI przechodza na zgodnej fiksturze
    e, w = run(chain_graph, schema)
    assert not e, e
    e, w = run(cn_graph, schema)
    assert not e, e
    print(f"OK 1: grafy UI zgodne ze schematem (ostrzezenia autogrow: {len(w)})")

    # 2. zamiana slotu wyjscia (CONDITIONING zamiast LATENT) -> TYPE_MISMATCH
    g = copy.deepcopy(cn_graph)
    ref_id = next(n["id"] for n in g["nodes"] if n["type"] == "MiniMaxH3ReferenceToVideo")
    for link in g["links"]:
        if link[5] == "LATENT" and link[1] == ref_id and link[2] == 1:
            link[2] = 0  # ustaw zly slot (CONDITIONING zamiast LATENT)
            break
    else:
        raise AssertionError("nie znaleziono linku LATENT z Ref2VA")
    e, _ = run(g, schema)
    assert "TYPE_MISMATCH" in [x["code"] for x in e], [x["code"] for x in e]
    print("OK 2: zly slot wyjscia wykryty (TYPE_MISMATCH)")

    # 3. plik ControlNet nieobecny na liscie -> COMBO_VALUE_NOT_ALLOWED
    e, _ = run(cn_graph, fixture(cn_options=("inny_plik.safetensors",)))
    cc = [x for x in e if x["code"] == "COMBO_VALUE_NOT_ALLOWED" and "ModelPatchLoader" in x["where"]]
    assert cc, [x["where"] for x in e]
    print("OK 3: brak pliku ControlNet na liscie -> COMBO_VALUE_NOT_ALLOWED")

    # 4. brakujacy plik wideo sterujacego -> blad na wezle LoadVideo
    e, _ = run(cn_graph, fixture(video_files=("control_shot_01.mp4",)))
    assert any(x["code"] == "COMBO_VALUE_NOT_ALLOWED" and "LoadVideo" in x["where"] for x in e)
    print("OK 4: brak wideo sterujacego -> blad LoadVideo")

    # 5. wymagane wejscie modelu niepodlaczone -> MISSING_LINK
    g = copy.deepcopy(chain_graph)
    for n in g["nodes"]:
        if n["type"] == "BasicGuider":
            for inp in n["inputs"]:
                if inp["name"] == "model":
                    inp["link"] = None
    e, _ = run(g, schema)
    assert "MISSING_LINK" in [x["code"] for x in e]
    print("OK 5: niepodlaczony model w BasicGuider -> MISSING_LINK")

    # 6. nieistniejaca klasa -> MISSING_NODE
    g = copy.deepcopy(chain_graph)
    g["nodes"][0]["type"] = "NieistniejacyWezel"
    e, _ = run(g, schema)
    assert "MISSING_NODE" in [x["code"] for x in e]
    print("OK 6: nieistniejaca klasa -> MISSING_NODE")

    # 7. zakres liczbowy: strength 11 > max 10
    g = copy.deepcopy(cn_graph)
    for n in g["nodes"]:
        if n["type"] == "MiniMaxH3FunControlNetApply":
            n["widgets_values"][0] = 11.0
            break
    e, _ = run(g, schema)
    assert "RANGE" in [x["code"] for x in e]
    print("OK 7: strength poza zakresem -> RANGE")

    # 8. format API: graf z repo przechodzi, a zly wybor modelu jest zlapany
    e, _ = v.validate_api(api_graph, schema)
    assert not e, e
    bad = copy.deepcopy(api_graph)
    bad["1"]["inputs"]["unet_name"] = "brak.safetensors"
    e, _ = v.validate_api(bad, schema)
    assert any(x["code"] == "COMBO_VALUE_NOT_ALLOWED" for x in e)
    print("OK 8: format API: zgodny graf przechodzi, zly model zlapany")

    # 9. wariant loadera tekstu: wartosc z listy przechodzi, wartosc spoza listy odrzucona
    te_value = "minimax_h3_pruned24_balanced: pruned24_balanced"
    te_schema = fixture()
    te_schema["MiniMaxH3TextEncoderLoader"] = {"input": {"required": {"text_encoder": [[te_value]]}},
                                               "output": ["CLIP"]}
    te_graph = json.load(open(os.path.join(ROOT, "workflows", "h3_chain_ui.json"), encoding="utf-8"))
    te_graph["nodes"][1]["type"] = "MiniMaxH3TextEncoderLoader"  # wezel 2 = tekst (CLIP)
    te_graph["nodes"][1]["widgets_values"] = [te_value]
    te_graph["nodes"][1]["outputs"] = [{"name": "CLIP", "type": "CLIP", "links": te_graph["nodes"][1]["outputs"][0]["links"], "slot_index": 0}]
    te_graph["nodes"][1]["inputs"] = []
    e, _ = run(te_graph, te_schema)
    assert not [x for x in e if x["code"] == "COMBO_VALUE_NOT_ALLOWED"], e
    te_graph["nodes"][1]["widgets_values"] = ["zla_nazwa: pruned24"]
    e, _ = run(te_graph, te_schema)
    assert any(x["code"] == "COMBO_VALUE_NOT_ALLOWED" for x in e)
    print("OK 9: wariant loadera tekstu: wartosc z listy OK, spoza listy odrzucona")

    print("\nWszystkie testy walidatora OK (na fiksturze, nie na Twoim ComfyUI).")


if __name__ == "__main__":
    main()
