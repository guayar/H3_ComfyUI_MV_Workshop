# Handoff: H3 Workshop (dla Claude i dla użytkownika)

Repo: `guayar/h3_comfyui_mv_workshop`, gałąź `h3-workflow-research`. Ten dokument opisuje stan, sposób użycia i sposób testowania. Dla każdej tezy podano status: **[ZWERYFIKOWANE]** (sprawdzone w kodzie, w testach lub w tej sesji), **[NIEZWERYFIKOWANE]** (czeka na test na R9700), **[DEKLARACJA]** (twierdzenie autora bez pomiaru).

---

## 1. Krótko: co jest i czego nie ma

Warsztat do długich, spójnych teledysków z MiniMax H3 Ref2VA w ComfyUI, na AMD Radeon AI PRO R9700 (ROCm).

**Jest:**
- grafy ComfyUI w formacie UI (`workflows/`), generowane skryptem `scripts/build_ui_chain.py`,
- wtyczka ComfyUI `custom_nodes/comfyui_h3_director/` (węzeł H3Director + panel planu w przeglądarce),
- narzędzia CPU: zszywanie ujęć, pomiar dryfu geometrii (affine i homografia), maska klapy, audyt runtime, walidator grafu offline,
- testy: 12 zestawów offline (`scripts/run_offline_tests.py`) oraz testy interfejsu panelu w Chromium.

**Nie ma (i nie da się tego zrobić bez ComfyUI, GPU lub zgody):**
- żadnego renderu na R9700 [NIEZWERYFIKOWANE: cały łańcuch generacji],
- uruchomionej wtyczki w ComfyUI [NIEZWERYFIKOWANE],
- pobranych wag modeli (brief wymaga zgody),
- zmierzonego dryfu na klatkach z H3,
- benchmarku VRAM i czasu (P5 z briefu, plan w `docs/NEXT_TESTS.md`).

---

## 2. Gdzie co leży

| Ścieżka | Rola |
|---|---|
| `workflows/h3_chain_ui.json` | 3 ujęcia Ref2VA, bez ControlNet, format UI |
| `workflows/h3_chain_controlnet_ui.json` | jak wyżej + Fun ControlNet (nazwa pliku z oficjalnego szablonu) |
| `workflows/h3_chain_refs_full_ui.json` | pełny zestaw referencji (9 obrazów, 3 wideo, 3 audio) |
| `workflows/h3_chain_from_plan_example.json` | graf wygenerowany z planu `examples/example_plan.json` |
| `workflows/h3_r2v_shot_api.json` | jedno ujęcie w formacie API (do wysyłania z Pythona) |
| `scripts/build_ui_chain.py` | generator grafów: `--shots --frames --controlnet --plan --extra-ref-images --ref-videos --ref-audios --text-encoder-value --audit` |
| `scripts/validate_graph_offline.py` | walidacja grafu względem zapisanego `/object_info` (bez serwera) |
| `scripts/audit_h3_runtime.py` | audyt runtime: węzły, pliki w listach, status `OK` / `MODEL_NOT_INSTALLED` / `SERVER_UNREACHABLE` |
| `scripts/stitch_shots.py` | zszywanie sekwencji PNG: Lab, dissolve, deflicker, `--blur-match`, eksport MP4 BT.709 |
| `scripts/measure_scene_drift.py` | pomiar dryfu na statycznych ROI, `--model affine|homography` |
| `scripts/make_control.py` | wideo sterujące z planu (krawędzie) i demo klapy (`--flap-demo`) |
| `scripts/int8_mm_microtest.py` | mikrotest int8 matmul, osobny proces, raportuje BLOCKED bez torch |
| `scripts/queue_shot.py` | wysyła graf API do serwera ComfyUI |
| `scripts/run_offline_tests.py` | uruchamia wszystkie testy offline |
| `custom_nodes/comfyui_h3_director/` | wtyczka: `__init__.py`, `h3_plan.py`, `h3_director_node.py`, `web/`, `tests/`, `examples/`, `README.md`, `INSTALL_AND_TEST.md` |
| `docs/HOW_TO_USE_UI.md` | instrukcja użycia grafów w UI |
| `docs/NEXT_TESTS.md` | kolejność testów T0–T8 na R9700 z progami |
| `docs/RESEARCH_DEEP.md` | research z etykietami źródeł (sekcje 1–12) |
| `docs/STITCH_WORKSHOP.md` | problemy zszywania i rozwiązania |
| `docs/RESEARCH_PARTIAL.md` | pierwsza runda researchu |

---

## 3. Środowisko i ograniczenia sesji

- **Brak w sesji:** serwera ComfyUI (`127.0.0.1:8188` nie odpowiada), torch, ROCm, GPU.
- **Dostępne:** Python 3 z numpy i Pillow, ffmpeg/ffprobe, Node 22 z Playwright i Chromium (`/opt/pw-browsers`), dostęp do GitHuba (w tym `raw.githubusercontent.com`).
- **Zablokowane domeny:** `huggingface.co`, `docs.comfy.org`, `runcomfy.com`. Nie zakładaj, że da się tam wejść. Jeśli użytkownik je odblokuje, sprawdź ponownie.
- **Nie instaluj** pakietów, wtyczek ani modeli bez zgody. Nie pobieraj wag.
- **Git:** push działa na tę gałąź. Commity podpisuj zgodnie z instrukcją sesji (`Co-Authored-By` i `Claude-Session`). Bez identyfikatora modelu w commitach i plikach repo.

---

## 4. Jak uruchomić testy lokalnie

Wszystko naraz (bez ComfyUI, na CPU, ok. kilka minut):
```bash
python3 scripts/run_offline_tests.py
```
Oczekiwany wynik: `12/12 zestawow OK`.

Pojedynczo:
```bash
python3 scripts/test_stitch.py                 # zszywanie, syntetyka
python3 scripts/test_sharpness_blur.py         # rozmycie całego ujęcia
python3 scripts/test_flap_mask.py              # maska klapy A–D
python3 scripts/test_measure_scene_drift.py    # dryf affine
python3 scripts/test_homography_drift.py       # dryf homografia
python3 scripts/test_audit_h3_runtime.py       # audyt na atrapie serwera
python3 scripts/test_validate_graph_offline.py # walidator na fiksturze schematu
python3 scripts/test_ref_limits.py             # limity referencji 9/3/3
python3 scripts/test_plan_graph.py             # plan -> graf
python3 custom_nodes/comfyui_h3_director/tests/test_h3_plan.py
python3 custom_nodes/comfyui_h3_director/tests/test_node_logic.py
node custom_nodes/comfyui_h3_director/tests/test_plan_core.js
node custom_nodes/comfyui_h3_director/tests/test_panel_ui.js   # Playwright + Chromium, 8 scenariuszy
```

**Uwaga o fiksturze:** `test_validate_graph_offline.py` używa ręcznie spisanego schematu. Sprawdza logikę walidatora, nie Twoją instalację. Prawdziwa walidacja wymaga `object_info.json` z działającego ComfyUI.

---

## 5. Jak użyć (przepływ pracy)

1. **Plan ujęć**: otwórz `custom_nodes/comfyui_h3_director/web/h3_director_panel.html` w przeglądarce. Ustaw długość, dodaj ujęcia (czas `12.5`, `1:02.5`), prompty, referencje po kolei. Pobierz `plan.json`.
2. **Graf z planu**: `python3 scripts/build_ui_chain.py --plan plan.json --out workflows/moj_graf.json`.
3. **Wtyczka w ComfyUI** (opcjonalnie): skopiuj `custom_nodes/comfyui_h3_director` do `ComfyUI/custom_nodes/`. Węzeł H3Director daje sloty referencji dla Ref2VA.
4. **Audyt przed generacją**: `python3 scripts/audit_h3_runtime.py --out h3_runtime_audit.json` (wymaga działającego ComfyUI). Bez `OK` nie buduj grafu ControlNet (`--audit`).
5. **Walidacja offline**: `python3 scripts/validate_graph_offline.py workflows/moj_graf.json --schema object_info.json`.
6. **Generacja** w ComfyUI: Workflow → Open → Queue. Wyniki PNG w `ComfyUI/output/h3/`.
7. **Zszywanie**: `python3 scripts/stitch_shots.py out/ folder1 folder2 --fade 12 --match-window 24 --blur-match --deflicker 9 --encode out/final.mp4`.
8. **Pomiar dryfu** na pierwszym ujęciu: `python3 scripts/measure_scene_drift.py --frames-dir folder1 --rois rois.json --out drift.json`. Plik `rois.json` to lista prostokątów na statycznej architekturze.

**Nie używaj SaveVideo do oceny** (miesza BT.601/709). Oceniaj PNG i zszywaj skryptem.

---

## 6. Jak testować na R9700 (dla użytkownika)

Pełna lista kontrolna jest w `custom_nodes/comfyui_h3_director/INSTALL_AND_TEST.md` (wtyczka, części A–E) oraz w `docs/NEXT_TESTS.md` (T0–T8, progi). Najkrócej:

1. **T0** testy offline: `python3 scripts/run_offline_tests.py`.
2. Uruchom ComfyUI, zapisz `object_info`: `curl -s http://127.0.0.1:8188/object_info > object_info.json`.
3. **T1** audyt: `python3 scripts/audit_h3_runtime.py`. Oczekiwany status `OK`.
4. **T2** mikrotest int8 w osobnym procesie: `python3 scripts/int8_mm_microtest.py`. Oczekiwany status `PASS`. Jeśli `FAIL`, zapisz wyjątek i wersje.
5. **T3** baseline: jedno ujęcie 124 klatek bez ControlNet. Obejrzyj klatki 1, środek, koniec. Bez szumu i mozaiki.
6. **T4** dryf na wyrenderowanym ujęciu, progi z `NEXT_TESTS.md`.
7. Dalej wg `NEXT_TESTS.md` (ControlNet, klapa, zszywanie, benchmark).

Nie ogłaszaj sukcesu sprzętowego bez obejrzenia klatek z R9700.

---

## 7. Status tez (zbiorczo)

| Teza | Status |
|---|---|
| Nazwy węzłów natywnych (`MiniMaxH3ReferenceToVideo`, `MiniMaxH3FunControlNetApply`, `ModelPatchLoader`, `LoadVideo`, `GetVideoComponents`, `LoadAudio`) | **[ZWERYFIKOWANE]** w kodzie `Comfy-Org/ComfyUI` (master) |
| Wyjścia Ref2VA: 0 = `positive`, 1 = `LATENT` | **[ZWERYFIKOWANE]** w kodzie |
| Limity referencji 9/3/3 | **[ZWERYFIKOWANE]** w kodzie |
| Nazwa pliku ControlNet `..._pruned_int8_convrot.safetensors` | **[ZWERYFIKOWANE w szablonie Comfy na GitHubie]**; obecność na Twojej maszynie **[NIEZWERYFIKOWANE]** (audyt) |
| Loader tekstu pruned24 (`MiniMaxH3TextEncoderLoader`) | **[ZWERYFIKOWANE]** w kodzie `kgonia`; działanie na ROCm **[NIEZWERYFIKOWANE]** |
| Recovered 8B nie nadaje się do Ref2VA | **[ZWERYFIKOWANE]** w kodzie (rzuca wyjątek przy obrazach) |
| `torch._int_mm` na gfx1201 działa lub nie | **[NIEZWERYFIKOWANE]** (mikrotest czeka na torch) |
| NVFP4 zawodzi lokalnie | **[NIEZWERYFIKOWANE]** (najpierw sprawdź, czy faktycznie zawodzi) |
| HybridWindows poprawia dryf | **[DEKLARACJA]**, kod istnieje, nie testowany |
| Orbit LoRA steruje kamerą | **[DEKLARACJA]** (model card) |
| Wyciszenie ruchu ust | **[NIEZWERYFIKOWANE]**; usunięcie audio nie usuwa ruchu ust |
| Zszywanie: skok L 25 → 0,5, chroma 15 → 0,6 | **[ZWERYFIKOWANE] na syntetyce**, nie na H3 |
| Pomiar dryfu: błąd < 0,05 px, homografia h31 ~1 % | **[ZWERYFIKOWANE] na syntetyce** |
| Wtyczka H3Director działa w ComfyUI | **[NIEZWERYFIKOWANE]** (import `app.js`, `None` na wyjściu) |
| Wyjścia `None` przy niepodłączonych slotach | **[NIEZWERYFIKOWANE]** w ComfyUI |
| Profil zszywania 1344×768: 39 s, 1,38 GB RSS (CPU) | **[ZWERYFIKOWANE]** w tej sesji |

---

## 8. Zasady pracy (obowiązują)

- **Kopia zapasowa** `workflows/` i `scripts/` przed większą edycją.
- **Nie instaluj** wtyczek i nie aktualizuj modeli bez zgody. Porównuj wersje z `/object_info` przed zmianami.
- **Nie pobieraj wag** bez zgody użytkownika.
- **Prompty H3: pozytywne zdania, bez negacji.** Zamiast „no speech” pisz opis: „the gardener is silent, lips softly closed”. Uwaga: placeholder w `build_ui_chain.py` nadal zawiera „no speech” (zadanie w sekcji 10).
- **PNG → BT.709** (ffmpeg), nie SaveVideo, do oceny.
- **Każdą tezę** oznaczaj statusem z sekcji 7 i podawaj źródło.
- **Nie raportuj sukcesu sprzętowego** bez obejrzenia klatek z gfx1201.
- **Walidację offline** traktuj jako dowód zgodności ze schematem, nie działania.

---

## 9. Pułapki, na które już trafiliśmy

Każda z nich została naprawiona. Warto pamiętać, żeby nie wrócić do starego błędu.

1. **Widgety UI nie są tylko wartościami.** `LoadImage` i `LoadVideo` w UI mają drugą wartość (`"image"`, `"video"`), a `RandomNoise` ma `control_after_generate`. Walidator to sprawdza.
2. **Liczba klatek musi być 17n+5.** 165 jest błędne (test to wyłapał). Poprawne: 124, 141, 158, 175, 192, 243.
3. **Metryka szwu** liczona ze średniej 24 klatek pogarszała wynik (dryf wewnątrz ujęcia). Statystyki są z 3 klatek przy szwie.
4. **Homografia i ROI**: współrzędne szablonu muszą być w pełnym kadrze (początek ROI). Bez tego wynik był błędny.
5. **Atrybut `disabled="null"`**: helper DOM zapisywał `null` jako tekst. Naprawione: `null` pomija atrybut.
6. **Import pakietu w testach**: klasa z pakietu i klasa z top-level to dwa obiekty. Porównuj po nazwie i atrybutach.
7. **Generator zapisał fałszywy graf**: raz zapisałem graf z fałszywym raportem audytu. Zregenerowany bez `--audit`. Zasada: nigdy nie zapisuj „zweryfikowanego” grafu bez prawdziwego audytu.
8. **Test wskazywał zły numer węzła** (zakładanie stałych ID zamiast wyszukiwania po typie). Szukaj po typie.

---

## 10. Co zrobić dalej (priorytety dla następnej sesji)

1. **Jeśli użytkownik zgłosi wynik testu wtyczki**: popraw według `INSTALL_AND_TEST.md` (numer kroku + treść błędu + wersja ComfyUI).
2. **Gdy będzie `object_info.json`**: zwaliduj wszystkie grafy (`workflows/*.json`) i napraw zgłoszone błędy.
3. **Gdy będzie torch z ROCm**: T2 (mikrotest int8), potem decyzja o loaderze tekstu.
4. **Gdy będzie działający Ref2VA**: T3, T4, potem zszywanie na prawdziwych klatkach (sprawdź progi z `NEXT_TESTS.md`).
5. **Otwarte w kodzie**: uint8 zamiast float32 w buforach zszywania (oszczędność ~4× RAM, dotąd nie zrobione); wyostrzanie w obu kierunkach; per-ujęciowe referencje w panelu (obecnie globalne).
6. **Placeholdery promptów** w `build_ui_chain.py` i w domyślnym tekście planu zawierają „no speech”. Zmień na opis pozytywny (patrz sekcja 8).
7. **Nie zrobione z briefu**: P5 (benchmark), sterowanie pozą (SDPose z szablonu), dynamiczna maska klapy w grafie (tylko demo w `make_control.py`).

---

## 11. Dla użytkownika w skrócie

- Zacznij od `python3 scripts/run_offline_tests.py` (oczekiwane: 12/12 OK).
- Wtyczka i jej test krok po kroku: `custom_nodes/comfyui_h3_director/INSTALL_AND_TEST.md`.
- Pełny plan testów na R9700 z progami: `docs/NEXT_TESTS.md`.
- Jeśli coś nie działa, zgłoś: numer kroku, wersję ComfyUI (`GET /system_stats`), treść błędu z konsoli serwera i przeglądarki.
