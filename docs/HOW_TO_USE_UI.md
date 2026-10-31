# Jak używać grafów H3 w ComfyUI (interfejs)

Ten dokument opisuje krok po kroku pracę z grafami w `workflows/`. Graf ma grupy kolorowe i notatkę w kanwie, więc wszystko jest widoczne na jednym ekranie.

> **Status:** grafy są zgodne ze schematem w walidatorze offline (na fiksturze), ale **nie uruchomione** na R9700. Pierwszy przebieg może wymagać poprawek (patrz sekcja 6).

---

## 1. Co jest w repo

| Plik | Do czego | Uwagi |
|---|---|---|
| `workflows/h3_chain_ui.json` | 3 ujęcia Ref2VA, bez ControlNet | najprostszy start |
| `workflows/h3_chain_controlnet_ui.json` | 3 ujęcia + Fun ControlNet | wymaga wideo sterującego i zainstalowanego pliku ControlNet |
| `workflows/h3_r2v_shot_ui.json` | jedno ujęcie | do szybkich testów |
| `workflows/h3_r2v_shot_api.json` | jedno ujęcie w formacie API | do wysyłania z Pythona, nie do wczytywania w UI |

Grafy generuje `scripts/build_ui_chain.py`. Liczbę ujęć i klatek zmienisz parametrami:
```bash
python3 scripts/build_ui_chain.py --shots 3 --frames 243 --out workflows/h3_chain_ui.json
python3 scripts/build_ui_chain.py --shots 2 --frames 124 --controlnet --out workflows/h3_chain_controlnet_ui.json
```

---

## 2. Otwieranie grafu

1. Uruchom ComfyUI.
2. Menu **Workflow → Open** (albo przeciągnij plik JSON na kanwę).
3. Pierwsza rzecz w kanwie to notatka „Instrukcja”. Przeczytaj ją.

Grupy na kanwie:
- **1. Modele i wejścia stałe** (zielona): modele, enkoder tekstu, referencje lokacji i postaci, opcjonalnie ControlNet.
- **Ujęcie N** (kolorowa): referencje, Ref2VA, próbkowanie, dekodowanie, zapis PNG. Ujęcia są obok siebie w tej samej kolejności, w jakiej powstają.
- **Notatka** (szara): instrukcja w kanwie.

---

## 3. Przed pierwszym uruchomieniem

1. Skopiuj do `ComfyUI/input/`:
   - `set_plate.png`: obraz lokacji (plan sceny),
   - `character_sheet.png`: arkusz postaci.
2. Jeśli używasz ControlNet: wygeneruj wideo sterujące i skopiuj do `input/`:
   ```bash
   python3 scripts/make_control.py set_plate.png --frames 243 --fps 24 \
       --out ~/ComfyUI/input/control_shot_01.mp4
   ```
   Powtórz dla każdego ujęcia (`control_shot_02.mp4`, ...).
3. Sprawdź modele. Każdy węzeł z listą wyboru pokazuje tylko pliki, które są zainstalowane. Jeśli Twojego pliku nie ma na liście, nie jest zainstalowany.

---

## 4. Ustawienia, które zmieniasz

Węzły podpisane „Ujęcie N: Ref2VA”:

| Pole | Co wpisać | Uwagi |
|---|---|---|
| `prompt` | jeden zwrot akcji, jeden ruch kamery albo statyw | pozytywne zdania, bez „nie” |
| `length` | 17n+5 | 124 ≈ 5 s, 243 ≈ 10 s |
| `ref_image_size` | `match` | `max` jest wolniejszy |
| `noise_seed` (węzeł „Ujęcie N: ziarno”) | liczba | ten sam seed = powtarzalny wynik |

Węzeł **Model patch: Fun ControlNet** (tylko wariant z ControlNet): wybierz plik z listy. Domyślna nazwa to kandydat z oficjalnego szablonu, ale **musi być na liście**.

Węzeł **Fun ControlNet** (w grupie każdego ujęcia): `strength` 1.0, `start_percent` 0.0, `end_percent` 1.0. Te wartości są nieprzetestowane.

---

## 5. Uruchomienie i wyniki

1. Kliknij **Queue Prompt** (lub Run).
2. Wyniki (PNG, po jednej klatce na plik) są w `ComfyUI/output/h3/`:
   - `shot_01_*.png`, `shot_02_*.png`, `shot_03_*.png`.
3. **Nie oceniaj wyniku przez wezeł SaveVideo.** Miesza kolory (BT.601 vs BT.709). Do MP4 zszywaj skryptem:
   ```bash
   python3 scripts/stitch_shots.py out/ <folder_ujecia_1> <folder_ujecia_2> <folder_ujecia_3> \
       --fade 12 --match-window 24 --blur-match --deflicker 9 --encode out/final.mp4
   ```
4. Zmierz dryf i ostrość na pierwszym ujęciu (`scripts/measure_scene_drift.py`), zanim przejdziesz do następnego.

---

## 6. Typowe problemy

| Objaw | Przyczyna | Co zrobić |
|---|---|---|
| Węzeł jest czerwony, „missing node” | brak custom node | zainstaluj wymagane pakiety (np. `MiniMaxH3FunControlNetApply` należy do natywnego H3) |
| Lista modeli jest pusta lub nie ma pliku | plik nie w `models/` | umieść plik w folderze i odśwież (R) |
| Połączenie czerwone | zły typ albo zły slot wyjścia | sprawdź, który slot jest „positive”, a który „LATENT” w węźle Ref2VA |
| Wideo sterujące nie wczytuje się | brak pliku w `input/` | skopiuj `control_shot_NN.mp4` i odśwież listę |
| Wynik zaszumiony lub zmozaikowany | ryzyko `torch._int_mm` na gfx1201 | patrz `docs/NEXT_TESTS.md` T2 (mikrotest int8) |

---

## 7. Ograniczenia tego grafu

- **Domyślnie** graf ma 3 obrazy na ujęcie (lokacja, postać, ostatnia klatka poprzedniego ujęcia).
- **Pełny zestaw referencji** (limity H3: 9 obrazów, 3 wideo, 3 audio) generuje się opcjami:
  ```bash
  python3 scripts/build_ui_chain.py --shots 3 --frames 243 --extra-ref-images 6 \
      --ref-videos 3 --ref-audios 3 --out workflows/h3_chain_refs_full_ui.json
  ```
  Dodatkowe pliki w `input/`: `extra_ref_image_01.png` ... `extra_ref_image_06.png`, `ref_video_01.mp4` ... `ref_video_03.mp4`, `ref_audio_01.wav` ... `ref_audio_03.wav`. Przy 3 ujęciach obrazów jest najwyżej 9 (pierwsze ujęcie ma 8). Generator odrzuca więcej.
- Audio wymaga co najmniej jednej referencji obrazu lub wideo (ograniczenie H3).
- Brak wyciszenia ust. Mowa i ruch ust mogą się pojawić mimo promptu (patrz `docs/RESEARCH_DEEP.md` §12.7).
- Brak dynamicznej maski klapy w grafie. Demo maski to osobny eksperyment (`scripts/make_control.py --flap-demo`).

---

## 8. Walidacja bez uruchamiania

Zapisz `object_info` raz, gdy ComfyUI działa:
```bash
curl -s http://127.0.0.1:8188/object_info > object_info.json
python3 scripts/validate_graph_offline.py workflows/h3_chain_controlnet_ui.json --schema object_info.json
```
Walidator pokaże brakujące pliki, złe typy połączeń i nieprawidłowe wartości list.
