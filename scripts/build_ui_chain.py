#!/usr/bin/env python3
"""Generuje graf ComfyUI (format UI, do wczytania przez Workflow > Open) dla lancucha ujec H3 Ref2VA.

Zasada zszywania: kazde kolejne ujecie dostaje jako referencje ostatnia klatke poprzedniego
ujecia (ref_image_2), obok stalych referencji lokacji (ref_image_0) i postaci (ref_image_1).
Dzieki temu kolejne ujecie zaczyna sie od tego samego wygladu sceny, a nie od dowolnej klatki.

Uzycie:
  python3 scripts/build_ui_chain.py                      # 3 ujecia, 243 klatki (~10,1 s)
  python3 scripts/build_ui_chain.py --shots 4 --frames 243 --out workflows/h3_chain_ui.json

Uzywane klasy (wszystkie potwierdzone w kodzie ComfyUI lub w oficjalnym szablonie):
  UNETLoader, CLIPLoader, VAELoader, LoadImage, MiniMaxH3ReferenceToVideo, BasicScheduler,
  KSamplerSelect, RandomNoise, BasicGuider, SamplerCustomAdvanced, VAEDecode,
  ImageFromBatch (rdzen ComfyUI), SaveImage (rdzen ComfyUI).

Wejscia w folderze input/ ComfyUI: set_plate.png, character_sheet.png.
"""
import argparse
import json

WIDTH, HEIGHT = 1344, 768
STEPS = 20


class Graph:
    def __init__(self):
        self.nodes = []
        self.links = []
        self.groups = []
        self.next_node = 1
        self.next_link = 1

    def group(self, title, bbox, color="#3f789e"):
        """Grupa wizualna w UI (format litegraph): bbox = [x, y, szer, wys]."""
        self.groups.append({"id": len(self.groups) + 1, "title": title, "bounding": list(bbox),
                            "color": color, "font_size": 24, "flags": {}})

    def add(self, cls, title, inputs, outputs, widgets, pos):
        nid = self.next_node
        self.next_node += 1
        self.nodes.append({
            "id": nid, "type": cls, "pos": list(pos), "size": [320, 110], "flags": {}, "order": nid, "mode": 0,
            "title": title,
            "inputs": [{"name": n, "type": t, "link": None} for n, t in inputs],
            "outputs": [{"name": n, "type": t, "links": [], "slot_index": i} for i, (n, t) in enumerate(outputs)],
            "properties": {"Node name for S&R": cls},
            "widgets_values": widgets,
        })
        return nid

    def connect(self, src, src_slot, dst, dst_input):
        s = self.node(src)
        d = self.node(dst)
        slot = s["outputs"][src_slot]
        ttype = slot["type"]
        idx = next(i for i, x in enumerate(d["inputs"]) if x["name"] == dst_input)
        lid = self.next_link
        self.next_link += 1
        slot["links"].append(lid)
        d["inputs"][idx]["link"] = lid
        self.links.append([lid, src, src_slot, dst, idx, ttype])

    def node(self, nid):
        return self.nodes[nid - 1]

    def to_ui(self):
        return {"last_node_id": self.next_node - 1, "last_link_id": self.next_link - 1,
                "nodes": self.nodes, "links": self.links, "groups": self.groups, "config": {}, "extra": {}, "version": 0.4}


# [OFFICIAL LIST, podane w briefie; nie pobrane w tej sesji] kandydat v1 INT8. Wymaga audytu runtime.
CONTROL_PATCH_FILE = "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors"


def build(shots, frames, controlnet=False, text_encoder_value=None, extra_images=0, ref_videos=0, ref_audios=0):
    g = Graph()
    last_index = frames - 1

    # --- wspolne zasoby (jedno zrodlo dla wszystkich ujec) ---
    unet = g.add("UNETLoader", "Model H3 Ref2VA", [], [("MODEL", "MODEL")],
                 ["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "default"], (0, 0))
    if text_encoder_value:
        # [CODE] wariant z kgonia/ComfyUI-MiniMaxH3TextEncoders: wartosc z listy audytu, nie zgadywac
        clip = g.add("MiniMaxH3TextEncoderLoader", "Text encoder (MiniMax H3 loader)", [], [("CLIP", "CLIP")],
                     [text_encoder_value], (0, 180))
    else:
        clip = g.add("CLIPLoader", "Text encoder Qwen3-VL", [], [("CLIP", "CLIP")],
                     ["qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "minimax", "default"], (0, 180))
    vae_v = g.add("VAELoader", "VAE wideo H3", [], [("VAE", "VAE")],
                  ["minimax_h3_video_vae_int8_convrot.safetensors"], (0, 360))
    vae_a = g.add("VAELoader", "VAE audio H3", [], [("VAE", "VAE")],
                  ["minimax_h3_audio_vae_fp32.safetensors"], (0, 540))
    set_plate = g.add("LoadImage", "Referencja: lokacja (stala)", [], [("IMAGE", "IMAGE"), ("MASK", "MASK")],
                      ["set_plate.png", "image"], (0, 720))
    character = g.add("LoadImage", "Referencja: postac (stala)", [], [("IMAGE", "IMAGE"), ("MASK", "MASK")],
                      ["character_sheet.png", "image"], (0, 900))
    sampler = g.add("KSamplerSelect", "Sampler", [], [("SAMPLER", "SAMPLER")], ["res_multistep"], (400, 0))
    sched = g.add("BasicScheduler", "Harmonogram krokow", [("model", "MODEL")], [("SIGMAS", "SIGMAS")],
                  ["simple", STEPS, 1], (400, 180))
    g.connect(unet, 0, sched, "model")

    g.add("MarkdownNote", "Instrukcja (przeczytaj najpierw)", [], [],
          [NOTE_TEXT], (-40, -560))
    g.group("1. Modele i wejscia stale (nie edytuj, poza nazwami plikow)", [-60, -60, 420, 1300], "#2d6a4f")
    # --- dodatkowe referencje (wspolne dla wszystkich ujec) ---
    # Limity H3 [CODE nodes_minimax_h3.py]: 9 obrazow, 3 wideo, 3 audio. Obrazy: 0 = lokacja, 1 = postac,
    # 2 = ostatnia klatka poprzedniego ujecia; dodatkowe od indeksu 3.
    extra_nodes = []  # (nazwa_wejscia, typ, id_wezla_zrodlowego)
    for k in range(extra_images):
        nid = g.add("LoadImage", f"Referencja dodatkowa obraz {k+1}", [], [("IMAGE", "IMAGE"), ("MASK", "MASK")],
                    [f"extra_ref_image_{k+1:02d}.png", "image"], (-420, 1300 + k * 140))
        extra_nodes.append((f"ref_image_{3 + k}", "IMAGE", nid, 0))
    for v in range(ref_videos):
        lv = g.add("LoadVideo", f"Referencja wideo {v+1}: plik", [], [("VIDEO", "VIDEO")],
                   [f"ref_video_{v+1:02d}.mp4", "video"], (-420, 1700 + v * 300))
        cv = g.add("GetVideoComponents", f"Referencja wideo {v+1}: klatki", [("video", "VIDEO")],
                   [("images", "IMAGE")], [], (-420, 1840 + v * 300))
        g.connect(lv, 0, cv, "video")
        extra_nodes.append((f"ref_video_{v}", "IMAGE", cv, 0))
    for a_i in range(ref_audios):
        la = g.add("LoadAudio", f"Referencja audio {a_i+1}", [], [("AUDIO", "AUDIO")],
                   [f"ref_audio_{a_i+1:02d}.wav", "audio"], (-420, 2600 + a_i * 140))
        extra_nodes.append((f"ref_audio_{a_i}", "AUDIO", la, 0))

    mp_loader = None
    if controlnet:
        mp_loader = g.add("ModelPatchLoader", "Model patch: Fun ControlNet (zweryfikuj audytem)", [],
                          [("MODEL_PATCH", "MODEL_PATCH")], [CONTROL_PATCH_FILE], (0, 1080))

    prev_last_frame = None
    for i in range(shots):
        col_x = 800 + i * 1500  # szerszy odstep: grupa ujecia + wezly ControlNet po lewej
        g.group(f"Ujecie {i+1}: referencje -> Ref2VA -> probkowanie -> zapis PNG",
                [col_x - 420, -60, 1380, 1320], ["#e76f51", "#2a9d8f", "#264653"][i % 3])
        row_y = 0
        seed = 261662374822964 + i
        ref_inputs = [("clip", "CLIP"), ("vae", "VAE"), ("audio_vae", "VAE"),
                      ("ref_image_0", "IMAGE"), ("ref_image_1", "IMAGE")]
        if prev_last_frame is not None:
            ref_inputs.append(("ref_image_2", "IMAGE"))
        for (nm, typ, _nid, _slot) in extra_nodes:
            ref_inputs.append((nm, typ))
        ref = g.add("MiniMaxH3ReferenceToVideo", f"Ujecie {i+1}: Ref2VA (SPRAWDZ WYJSCIA)",
                    ref_inputs,
                    [("CONDITIONING", "CONDITIONING"), ("LATENT", "LATENT")],
                    [f"SHOT {i+1} PROMPT: one story beat, named camera, no speech", WIDTH, HEIGHT, frames, "match"],
                    (col_x, row_y))
        g.connect(clip, 0, ref, "clip")
        g.connect(vae_v, 0, ref, "vae")
        g.connect(vae_a, 0, ref, "audio_vae")
        g.connect(set_plate, 0, ref, "ref_image_0")
        g.connect(character, 0, ref, "ref_image_1")
        if prev_last_frame is not None:
            g.connect(prev_last_frame, 0, ref, "ref_image_2")
        for (nm, _typ, nid, slot) in extra_nodes:
            g.connect(nid, slot, ref, nm)

        noise = g.add("RandomNoise", f"Ujecie {i+1}: ziarno", [], [("NOISE", "NOISE")],
                      [seed, "fixed"], (col_x, row_y + 280))
        guider = g.add("BasicGuider", f"Ujecie {i+1}: guider", [("model", "MODEL"), ("conditioning", "CONDITIONING")],
                       [("GUIDER", "GUIDER")], [], (col_x, row_y + 420))
        model_for_guider = unet
        if controlnet:
            # sterowanie per ujecie: wideo z folderu input/ -> klatki IMAGE -> patch na modelu
            cv = g.add("LoadVideo", f"Ujecie {i+1}: wideo sterujace", [], [("VIDEO", "VIDEO")],
                       [f"control_shot_{i+1:02d}.mp4", "video"], (col_x - 400, row_y + 100))
            cc = g.add("GetVideoComponents", f"Ujecie {i+1}: klatki sterujace", [("video", "VIDEO")],
                       [("images", "IMAGE")], [], (col_x - 400, row_y + 240))
            g.connect(cv, 0, cc, "video")
            fc = g.add("MiniMaxH3FunControlNetApply", f"Ujecie {i+1}: Fun ControlNet",
                       [("model", "MODEL"), ("model_patch", "MODEL_PATCH"), ("vae", "VAE"),
                        ("control_video", "IMAGE")],
                       [("MODEL", "MODEL")], [1.0, 0.0, 1.0], (col_x - 400, row_y + 380))
            g.connect(unet, 0, fc, "model")
            g.connect(mp_loader, 0, fc, "model_patch")
            g.connect(vae_v, 0, fc, "vae")
            g.connect(cc, 0, fc, "control_video")
            model_for_guider = fc
        g.connect(model_for_guider, 0, guider, "model")
        g.connect(ref, 0, guider, "conditioning")
        samp = g.add("SamplerCustomAdvanced", f"Ujecie {i+1}: probkowanie",
                     [("noise", "NOISE"), ("guider", "GUIDER"), ("sampler", "SAMPLER"),
                      ("sigmas", "SIGMAS"), ("latent_image", "LATENT")],
                     [("output", "LATENT"), ("denoised_output", "LATENT")], [], (col_x, row_y + 560))
        g.connect(noise, 0, samp, "noise")
        g.connect(guider, 0, samp, "guider")
        g.connect(sampler, 0, samp, "sampler")
        g.connect(sched, 0, samp, "sigmas")
        g.connect(ref, 1, samp, "latent_image")

        dec = g.add("VAEDecode", f"Ujecie {i+1}: dekodowanie", [("samples", "LATENT"), ("vae", "VAE")],
                    [("IMAGE", "IMAGE")], [], (col_x, row_y + 760))
        g.connect(samp, 0, dec, "samples")
        g.connect(vae_v, 0, dec, "vae")

        g.add("SaveImage", f"Ujecie {i+1}: zapis klatek PNG", [("images", "IMAGE")], [], [f"h3/shot_{i+1:02d}"],
              (col_x, row_y + 900))
        g.connect(dec, 0, g.next_node - 1, "images")

        if i < shots - 1:
            last = g.add("ImageFromBatch", f"Ujecie {i+1}: ostatnia klatka -> ref dla ujecia {i+2}",
                         [("image", "IMAGE")], [("IMAGE", "IMAGE")], [last_index, 1], (col_x, row_y + 1040))
            g.connect(dec, 0, last, "image")
            prev_last_frame = last

    g.group("Notatka (ponizej: instrukcja)", [-60, -620, 1400, 520], "#555555")
    return g.to_ui()


NOTE_TEXT = """# H3 Ref2VA: lancuch ujec (jak uzywac)

**Przed startem**
1. Wrzuc do folderu `ComfyUI/input/`: `set_plate.png` (lokacja) i `character_sheet.png` (postac).
2. Jesli uzywasz ControlNet: wideo sterujace `control_shot_01.mp4` ... (generuje `scripts/make_control.py`).
3. W wezlu **Model patch** wybierz plik z listy (musi byc zainstalowany). Nie zmieniaj nazwy recznie.

**Ustawienia ujecia (wezly "Ujecie N: Ref2VA")**
- `prompt`: jeden zwrot akcji, jeden nazwany ruch kamery albo zablokowany statyw. Zdania pozytywne, bez „nie”.
- `length`: 17n+5 (np. 124 = ok. 5 s, 243 = ok. 10 s).
- `ref_image_size`: `match` (domyslnie). `max` jest wolniejszy.
- `noise_seed`: ten sam seed daje powtarzalny wynik.

**Wyniki**
- Klatki PNG: `ComfyUI/output/h3/shot_01_*.png` (kolejne ujecia: shot_02, shot_03).
- Nie uzywaj wezla SaveVideo do oceny (miesza kolory BT.601/709). Zszywanie i MP4 robi `scripts/stitch_shots.py` (BT.709).

**Ograniczenia**
- Referencje w tym grafie: obraz lokacji, obraz postaci i ostatnia klatka poprzedniego ujecia (3 obrazy). Pelny zestaw (do 9 obrazow, 3 wideo, 3 audio) generuje `--extra-ref-images`, `--ref-videos`, `--ref-audios`. Audio wymaga referencji obrazu lub wideo.
- Wszystkie wezly musza byc zainstalowane. Walidacja: `scripts/validate_graph_offline.py`.
"""

def check_control_file(audit_path):
    """Fail-fast: nie zapisuj grafu ControlNet, jesli raport audytu nie potwierdza pliku."""
    with open(audit_path, encoding="utf-8") as fh:
        rep = json.load(fh)
    if rep.get("status") == "SERVER_UNREACHABLE":
        raise SystemExit("SERVER_UNREACHABLE: audyt nie potwierdza pliku (serwer nieosiagalny). Uruchom ComfyUI i powtorz audyt.")
    entries = [f for f in rep.get("files", []) if f.get("expected") == CONTROL_PATCH_FILE]
    if not entries or entries[0].get("status") != "OK":
        raise SystemExit(f"MODEL_NOT_INSTALLED: {CONTROL_PATCH_FILE} nie figuruje w ModelPatchLoader.name. "
                         "Nie podstawiam innej nazwy; zainstaluj plik albo wybierz zgodny z listy audytu.")
    print(f"audyt potwierdza: {CONTROL_PATCH_FILE}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", type=int, default=3, help="liczba ujec w lancuchu (domyslnie 3)")
    parser.add_argument("--frames", type=int, default=243,
                        help="klatki na ujecie, musi byc 17n+5 (243 = ~10,1 s przy 24 fps)")
    parser.add_argument("--out", default="workflows/h3_chain_ui.json")
    parser.add_argument("--audit", help="raport z scripts/audit_h3_runtime.py; bez zgodnego pliku graf nie zostanie zapisany")
    parser.add_argument("--text-encoder-value",
                        help="wartosc text_encoder z audytu (np. '<katalog>: <wariant pruned24>'); zamiast NVFP4 CLIPLoader")
    parser.add_argument("--extra-ref-images", type=int, default=0,
                        help="dodatkowe obrazy referencji (plik input/extra_ref_image_NN.png), maks. 6 przy wielu ujeciach")
    parser.add_argument("--ref-videos", type=int, default=0, choices=range(0, 4),
                        help="referencje wideo (input/ref_video_NN.mp4), limit H3: 3")
    parser.add_argument("--ref-audios", type=int, default=0, choices=range(0, 4),
                        help="referencje audio (input/ref_audio_NN.wav), limit H3: 3. Wymagaja referencji obrazu lub wideo")
    parser.add_argument("--controlnet", action="store_true",
                        help="dodaj Fun ControlNet: na ujecie wideo input/control_shot_NN.mp4 (patrz scripts/make_control.py)")
    args = parser.parse_args()
    if args.frames % 17 != 5:
        parser.error("--frames musi byc w siatce 17n+5, np. 124, 192, 243")
    if args.controlnet and args.audit:
        check_control_file(args.audit)
    elif args.controlnet:
        print("UWAGA: brak --audit; nazwa pliku ControlNet NIEZWERYFIKOWANA w tym srodowisku")
    max_images = 9
    base_images = 2 + (1 if args.shots > 1 else 0)
    if base_images + args.extra_ref_images > max_images:
        parser.error(f"obrazow referencji najwyzej {max_images}: {base_images} stale + {args.extra_ref_images} dodatkowe")
    wf = build(args.shots, args.frames, args.controlnet, args.text_encoder_value,
               extra_images=args.extra_ref_images, ref_videos=args.ref_videos, ref_audios=args.ref_audios)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, ensure_ascii=False, indent=1)
    print(f"zapisano {args.out}: {len(wf['nodes'])} wezlow, {len(wf['links'])} polaczen")


if __name__ == "__main__":
    main()
