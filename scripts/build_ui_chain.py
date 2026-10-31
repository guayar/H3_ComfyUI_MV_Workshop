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
        self.next_node = 1
        self.next_link = 1

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
                "nodes": self.nodes, "links": self.links, "groups": [], "config": {}, "extra": {}, "version": 0.4}


def build(shots, frames):
    g = Graph()
    last_index = frames - 1

    # --- wspolne zasoby (jedno zrodlo dla wszystkich ujec) ---
    unet = g.add("UNETLoader", "Model H3 Ref2VA", [], [("MODEL", "MODEL")],
                 ["minimax_h3_ref2va_pruned_int8_convrot.safetensors", "default"], (0, 0))
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

    prev_last_frame = None
    for i in range(shots):
        col_x = 800 + i * 1100
        row_y = 0
        seed = 261662374822964 + i
        ref_inputs = [("clip", "CLIP"), ("vae", "VAE"), ("audio_vae", "VAE"),
                      ("ref_image_0", "IMAGE"), ("ref_image_1", "IMAGE")]
        if prev_last_frame is not None:
            ref_inputs.append(("ref_image_2", "IMAGE"))
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

        noise = g.add("RandomNoise", f"Ujecie {i+1}: ziarno", [], [("NOISE", "NOISE")],
                      [seed, "fixed"], (col_x, row_y + 280))
        guider = g.add("BasicGuider", f"Ujecie {i+1}: guider", [("model", "MODEL"), ("conditioning", "CONDITIONING")],
                       [("GUIDER", "GUIDER")], [], (col_x, row_y + 420))
        g.connect(unet, 0, guider, "model")
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

    return g.to_ui()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", type=int, default=3, help="liczba ujec w lancuchu (domyslnie 3)")
    parser.add_argument("--frames", type=int, default=243,
                        help="klatki na ujecie, musi byc 17n+5 (243 = ~10,1 s przy 24 fps)")
    parser.add_argument("--out", default="workflows/h3_chain_ui.json")
    args = parser.parse_args()
    if args.frames % 17 != 5:
        parser.error("--frames musi byc w siatce 17n+5, np. 124, 192, 243")
    wf = build(args.shots, args.frames)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(wf, fh, ensure_ascii=False, indent=1)
    print(f"zapisano {args.out}: {len(wf['nodes'])} wezlow, {len(wf['links'])} polaczen")


if __name__ == "__main__":
    main()
