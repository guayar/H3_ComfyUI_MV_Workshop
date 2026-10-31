# Następne testy: kolejność, kryteria, blokady

Cel: sprawdzić na R9700 (gfx1201, ROCm), czy łańcuch Ref2VA + Fun ControlNet + zszywanie daje mierzalnie stabilną geometrię i kolor. Każdy test ma metrykę i próg. **Progi są prowizoryczne** i trzeba je skalibrować na własnym planie.

Oznaczenia: `[CODE]` sprawdzone w kodzie, `[AUTHOR]` deklaracja, `[USER REPORT]` zgłoszenie, `[UNVERIFIED]` nieprzetestowane na tej maszynie.

---

## 0. Stan blokad w tym środowisku (zapisany 2026-10-31)

| Element | Stan | Co odblokuje |
|---|---|---|
| Serwer ComfyUI `127.0.0.1:8188` | **nieosiągalny** (`scripts/audit_h3_runtime.py` → SERVER_UNREACHABLE) | uruchomienie ComfyUI na R9700 |
| torch, ROCm | **brak** (`scripts/int8_mm_microtest.py` → BLOCKED) | środowisko torch z ROCm |
| `huggingface.co`, `docs.comfy.org`, `runcomfy.com` | **zablokowane** w sesji | dodanie domen w ustawieniach sesji |
| Wagi H3, plik ControlNet | **nie pobrane** (brief: bez zgody nie pobieramy) | zgoda użytkownika |
| Renderowanie na GPU | **niewykonane** | wszystko powyżej |

Nic z sekcji 1–5 nie zostało uruchomione na GPU. Testy są na CPU (numpy, Pillow, ffmpeg) i na danych syntetycznych.

---

## 1. Kolejność testów (najmniejsze pierwsze)

### T1. Audyt runtime (5 min)
```bash
python3 scripts/audit_h3_runtime.py --url http://127.0.0.1:8188 --out h3_runtime_audit.json
```
**Kryterium:** status `OK`. Każdy inny status ma konkretną akcję w polu `unmet`.
**Bramka:** bez `OK` nie generujemy grafu ControlNet.

### T2. Mikrotest int8 matmul (5 min, osobny proces)
```bash
python3 scripts/int8_mm_microtest.py --out int8_microtest.json
```
**Kryterium:** `status: PASS`, `max_abs_diff == 0` we wszystkich kształtach, także `(33, 47, 19)`.
**Uwaga:** PASS nie dowodzi, że cały potok int8 H3 działa. Tylko mikrotest.

### T3. Ref2VA bez ControlNet (baseline, 124 klatki)
Graf: `workflows/h3_chain_ui.json`, jedno ujęcie (ustaw `--shots 1 --frames 124`).
```bash
python3 scripts/build_ui_chain.py --shots 1 --frames 124 --out /tmp/baseline.json
```
**Kryteria:**
- wyjście bez szumu i mozaiki (widoczne na 3 klatkach z początku, środka, końca),
- wszystkie 124 klatki zapisane jako PNG,
- zapisany czas renderu i szczytowe VRAM (`rocm-smi` w trakcie).

### T4. Pomiar dryfu na jednym ujęciu (bez zmian w grafie)
```bash
python3 scripts/measure_scene_drift.py --frames-dir <folder_ujecia> \
    --rois rois.json --exclude-mask moving_mask.png --out drift_baseline.json
```
Plik `rois.json` ustawiasz na klatkę referencyjną z planu (okno, kominek, poręcz, górna ściana).

**Kryteria** (PROWIZORYCZNE, [UNVERIFIED] na H3):

| Metryka | Próg |
|---|---|
| `max_abs_scale_drift` | ≤ 0,002 |
| `max_shift_px` | ≤ 0,5 |
| `max_residual_local_px` | ≤ 0,5 |
| `min_confidence` | ≥ 0,95 |

Wynik `frames_flagged` > 0 oznacza, że trzeba zbadać klatki z flagą, zanim przejdziesz dalej.

### T5. Fun ControlNet: geometria bez maski (wariant A)
1. Wygeneruj wideo sterujące planu:
   ```bash
   python3 scripts/make_control.py set_plate.png --frames 124 --fps 24 \
       --out ~/ComfyUI/input/control_shot_01.mp4
   ```
2. Sprawdź w audycie (`controlnet_candidates`, pole `available: true`), czy plik `minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors` jest w liście. Nazwa pochodzi z oficjalnego szablonu Comfy, ale obecność na maszynie trzeba potwierdzić.
3. Zbuduj graf z audytem:
   ```bash
   python3 scripts/build_ui_chain.py --shots 1 --frames 124 --controlnet \
       --audit h3_runtime_audit.json --out workflows/h3_cn_test.json
   ```
   Generator odmówi zapisu, jeśli plik nie jest w liście. To jest zamierzone.
4. Uruchom i zmierz jak w T4.

**Kryterium względne:** skala i przesunięcie ControlNet **nie gorsze** niż baseline T3, a ostrość w pasie górnym **nie spada** o więcej niż 5 %. Jeśli jest lepiej, a ostrość spada, zanotuj to i nie zakładaj sukcesu.

### T6. Dynamiczna maska klapy (eksperyment, bez wniosków o fizyce)
```bash
python3 scripts/make_control.py set_plate.png --flap-demo flap_demo \
    --flap-rect 60,100,80,50 --flap-frames 124 --flap-stem 50
```
Obejrzyj `flap_demo/preview_contact_sheet.png` i `flap_demo/preview_control.gif`.

Warianty do uruchomienia w ComfyUI (pliki gotowe w `flap_demo/`):
- **A** `A_geometry` – sterowanie geometrią,
- **B** `B_mask_source` – maska i źródło (wymaga węzła z `mask` i `source_video`),
- **C** `C_combined` – wszystko razem,
- **D** `D_baseline` – bez sterowania (jak T3).

**Kryteria:** klapa i łodyga są **ciągłe** w czasie (brak czarnych dziur, brak rozmazanych fragmentów), a podłoga poza klapą nie zmienia geometrii (T4 na ROI podłogi poza klapą). **Nie zakładamy**, że H3 odtworzy zawias i cień.

### T7. Zszywanie na prawdziwych ujęciach
Dwa ujęcia z T3 (lub dwa kolejne z łańcucha). Wynik PNG → skrypt:
```bash
python3 scripts/stitch_shots.py out/ shot_01 shot_02 \
    --fade 12 --match-window 24 --blur-match --deflicker 9 --encode out/final.mp4
```
Flaga `--blur-match` rozmywa **całe** nowe ujęcie jedną sigmą (wyznaczoną binarnie), gdy jest ostrzejsze. Sigma jest zapisana w raporcie (`blur_sigma_whole_shot`).

**Kryteria szwu** (z raportu `stitch_report.json`):
- `L_jump` po ≤ 1,0 (było ≈ 25 na syntetyce),
- `chroma_jump` po ≤ 1,0,
- `sharp_ratio_head_over_tail` po w przedziale 0,9–1,1 przy aktywnym `blur_match`.

**Bramka człowieka:** każdy szew oglądasz przed kolejnym ujęciem.

### T8. Benchmark porównawczy (opcjonalny, tylko po T3–T7)
Dwa ujęcia: baseline, ControlNet, mask-prototyp, HybridWindows (jeśli zależności są zainstalowane). Te same referencje, seed, długość, sampler, rozdzielczość i ROI.
**Mierz:** czas renderu i szczytowe VRAM. **Nie zakładaj**, że współdzielone odszumianie naprawia perspektywę – to trzeba zmierzyć metryką T4.

---

## 2. Blokady, które wstrzymują T1–T8

- **T1, T5** wymagają działającego ComfyUI. Bez niego nie wiemy, czy plik ControlNet jest zainstalowany.
- **T2** wymaga torch z ROCm w osobnym środowisku (nie w środowisku ComfyUI).
- **T3–T8** wymagają wag H3 na dysku (duże pliki, potrzebna zgoda).
- **T6 wariant B/C** wymaga węzła z wejściami `mask` i `source_video` (natywny `MiniMaxH3FunControlNetApply`). Sprawdź audytem.
- **HybridWindows** wymaga MMH3Tools; nie jest zainstalowany ani sprawdzony na R9700.

---

## 3. Polecenia z tego środowiska (bez GPU, do powtórzenia)

```bash
python3 scripts/test_stitch.py                 # zszywanie, syntetyka
python3 scripts/test_sharpness_blur.py         # rozmycie całego ujęcia
python3 scripts/test_flap_mask.py              # maska klapy A–D
python3 scripts/test_measure_scene_drift.py    # pomiar dryfu ze znanymi przekształceniami
python3 scripts/test_audit_h3_runtime.py       # audyt na atrapie serwera
```

Wszystkie pięć testów przeszły 2026-10-31 (exit 0).
