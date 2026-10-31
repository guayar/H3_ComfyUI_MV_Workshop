# Warsztat zszywania ujęć (H3, AMD R9700)

Jak łączyć ujęcia z MiniMax H3 w jeden ciąg bez widocznych szwów. Narzędzie: `scripts/stitch_shots.py`. Test bez GPU: `scripts/test_stitch.py`.

> Status: skrypt i test działają na danych syntetycznych. **Nie testowano jeszcze na prawdziwych klatkach H3.** Każdy wynik na H3 trzeba zmierzyć.

---

## 1. Przepływ pracy

1. **Wygeneruj ujęcia** w ComfyUI (np. `workflows/h3_chain_ui.json`). Każde ujęcie zapisz jako sekwencję PNG w osobnym folderze.
2. **Zszyj:**
   ```bash
   python3 scripts/stitch_shots.py out/ shot_01 shot_02 shot_03 \
       --fade 12 --match-window 24 --sharpen --deflicker 9 --encode out/final.mp4
   ```
3. **Sprawdź** `out/stitch_report.json`: skoki przed i po korekcie na każdym szwie oraz stosunek ostrości.
4. **Zatwierdź** każdy szew oglądem (bramka człowieka z briefu) przed kolejnym ujęciem.

Parametry:
- `--fade N`: długość przejścia (dissolve) w klatkach. Domyślnie 12 (0,5 s).
- `--match-window N`: ile klatek wygaszać korektę koloru po szwie. Domyślnie 24.
- `--sharpen`: wyostrz nowe ujęcie, jeśli jest miększe od poprzedniego.
- `--deflicker N`: wygładź jasność w całym ciągu (okno N klatek). 0 = wyłączone.
- `--band`: wysokość górnego pasa kadru, na którym liczona jest ostrość (domyślnie 0,15).

---

## 2. Problemy i rozwiązania

| Problem | Przyczyna | Rozwiązanie w skrypcie | Źródło / status |
|---|---|---|---|
| **Czerwony/pomarańczowy skok koloru** na szwie | Różnica chrominancji a/b między ujęciami. Korekta samą jasnością zostawia skok koloru. | Dopasowanie średniej i odchylenia w **Lab** (osobno L, a, b) na 3 klatkach przy szwie. | Zgłoszenie: korekta tylko w jasności zostawia chrominancję ([tritant#106](https://github.com/tritant/ComfyUI_MiniMax_H3_Extender/issues/106)). **Test syntetyczny:** chrominancja 15 → 0,6. |
| **Czerwień zmienia się w pomarańcz przy odtwarzaniu** | FFmpeg konwertuje RGB→YUV wg BT.601, a odtwarzacz zakłada BT.709. | Kodowanie z `scale=out_color_matrix=bt709` i tagami BT.709. | Opis problemu ([FFmpeg-user](https://ffmpeg.org/pipermail/ffmpeg-user/2012-July/007833.html)). **Test:** MP4 ma `bt709` w trzech tagach. |
| **Skok jasności** na szwie | Różna ekspozycja ujęć, mrugnięcie jasności. | Ta sama korekta Lab (kanał L). | [Dev.to: grade-match](https://dev.to/humzakt/seam-free-video-splicing-grade-match-end-frame-interpolation-and-karaoke-captions-3dl0). **Test:** L 25 → 0,5. |
| **Migotanie / blyski jasności** w ciągu | Każdy klip ma własną ekspozycję. | `--deflicker`: ruchoma średnia jasności, klatka skalowana do średniej. | [Queststudio](https://queststudio.io/blog/reduce-flicker-melting-artifacts). **Test:** maks. skok średniej L 1,79 → 1,50. |
| **Ostrość spada** po każdym przedłużeniu (12–40 % wg briefu) | Każdy przebieg dyfuzji wygładza detal. | `--sharpen`: maska wyostrzająca na nowym ujęciu, gdy ma niższy stosunek ostrości. Siła ograniczona do 0,6. | Brief: LMS LoRA w oknach. **Ograniczenie:** wyostrzanie nie odtwarza utraconego detalu. |
| **Przeskok** między ujęciami | Brak przejścia między klatkami. | Dissolve cosinusowy (`--fade`) z ostatnich klatek poprzedniego ujęcia. | [Artokun: nakładanie klatek](https://artokun.mintlify.app/blog/video-extend-pusa-comfyui), [Dev.to](https://dev.to/humzakt/seam-free-video-splicing-grade-match-end-frame-interpolation-and-karaoke-captions-3dl0). Przy nakładce usuń zduplikowane klatki po obu stronach. |
| **Dryf koloru** wzdłuż łańcucha | Każde ujęcie dziedziczy odchylenie poprzedniego. | Korekta względem poprzedniego ujęcia (nie względem pierwszego). Pierwsze ujęcie to wzorzec. | [Artokun](https://artokun.mintlify.app/blog/video-extend-pusa-comfyui): „color/exposure drift to najczęstszy artefakt”. |
| **Dryf geometrii** (skala, przesunięcie kadru) | Model nie utrzymuje geometrii wnętrza między ujęciami. | **Nie rozwiązane tym skryptem.** Potrzebny ControlNet (natywny `MiniMaxH3FunControlNetApply`) albo stała kamera, plus pomiar ECC. | Brief, sekcja 4. |
| **Ruch ust / mowa** przy cichej referencji | H3 generuje audio razem z wideo. | Poza skryptem. Wyłącz audio przy montażu (`-an` w ffmpeg) i mierz ruch ust osobno. | [tritant#28 w LongMedia](https://github.com/vizart-vj/ComfyUI-MiniMax-H3-LongMedia/issues/28). |

**Uwaga o metryce:** pierwsza wersja korekty liczyła statystyki z 24 klatek i pogarszała skok jasności (25 → 4). Dryf wewnątrz ujęcia podnosił średnią. Dlatego statystyki liczone są z 3 klatek przy samym szwie. Ta zasada jest sprawdzona testem.

---

## 3. Co sprawdza test (`scripts/test_stitch.py`)

Syntetyczne ujęcia: trzy ujęcia z tym samym tłem. Ujęcie 2: czerwony odcień, jaśniejsze, rozmyte. Ujęcie 3: żółty odcień, ciemniejsze.

- Liczba klatek zgodna ze wzorem: `(N - keep) + 2·(N - fade) + keep`.
- Skok L i chrominancji na każdym szwie po korekcie jest mniejszy niż przed korektą.
- Deflicker nie zwiększa największego skoku średniej jasności.

**Co test NIE sprawdza:** realnego wyglądu H3, dryfu geometrii, ostrości na prawdziwych klatkach.

---

## 4. Alternatywy dla NVFP4 (text encoder, AMD)

Problem: `qwen3vl_32b_minimax_h3_nvfp4_awq` używa NVFP4. Źródła nie są zgodne co do wymogu Blackwell. Do wyboru:

| Wariant | Rozmiar | Uwagi | Źródło |
|---|---|---|---|
| **BF16** (referencja) | ~63 GiB | Nie zmieści się w 32 GB VRAM bez offloadu. | [vLLM recipe](https://recipes.vllm.ai/MiniMaxAI/MiniMax-H3) |
| **INT8 ConvRot, 24 warstwy** (pruned) | ~15,2 GiB | Mieści się w VRAM. Autor deklaruje podobieństwo kondycjonowania 0,99999 do NVFP4 (**deklaracja, nie pomiar**). | [SearchingMan/MiniMax-H3-Text-Encoders](https://huggingface.co/SearchingMan/MiniMax-H3-Text-Encoders) |
| **8B BF16 „recovered”** | ~10,6 GiB | To inny model (Qwen3-VL-8B), więc kondycjonowanie się zmieni. Nie jest to zamiennik 1:1. | [SearchingMan](https://huggingface.co/SearchingMan/MiniMax-H3-Text-Encoders) |
| **FP8 „radiance” dla RDNA4** | ~60,5 GiB | Społeczność, format kontenera nieznany w ComfyUI. Nie uruchamiać bez przeglądu. | [StillDeadcode](https://huggingface.co/StillDeadcode/minimax-h3-fp8) |

**Rekomendacja do testu:** INT8 ConvRot 24 warstwy. Zanim go użyjesz, sprawdź, czy model H3 `int8_convrot` nie korzysta z `torch._int_mm`, bo według researchu ta funkcja była zepsuta na gfx1201.

---

## 5. Czego brakuje (następne kroki)

1. **Pomiar drogi kamery i geometrii** metodą ECC na pasie górnym (brief, sekcja 5). Skrypt tego jeszcze nie robi.
2. **Test na prawdziwych klatkach H3** z jednego ujęcia i dwóch sąsiadujących.
3. **Wyostrzanie w obie strony:** obecnie tylko wzmacnia miękkie ujęcie. Jeśli nowe jest ostrzejsze, trzeba je rozmyć (nie zrobione).
4. **Walidacja na R9700:** uruchomienie tego skryptu jest czysto CPU (numpy, Pillow), więc nie zależy od ROCm.

---

## 6. Rozmycie całego ujęcia (`--blur-match`, P4)

Gdy **nowe ujęcie jest ostrzejsze** od poprzedniego, skrypt rozmywa **całe** ujęcie jedną sigmą (rozmycie Gaussa). Sigmę wyznacza binarny podział tak, żeby wariancja Laplace'a pasa górnego trafiła w wartość poprzedniego ujęcia. Sigma jest taka sama dla każdej klatki ujęcia, więc nie ma migotania.

- Działa tylko w jedną stronę (rozmywa ostrzejsze). Wyostrzanie miękkiego ujęcia (`--sharpen`) działa osobno i zanika w oknie `--match-window`.
- Nie dotyka ruchomego pierwszego planu poza górnym pasem. Test 5 w `scripts/test_sharpness_blur.py` to sprawdza.
- Nie przywraca utraconych detali. Wyrównuje tylko ostrość.
- Raport zawiera `blur_sigma_whole_shot`, `lapvar_tail_ref` i `lapvar_head_before` dla każdego szwu.

**Status:** testy syntetyczne przechodzą (stosunek ostrości 1697 → 0,98 przy sigmie 1,59). **Nie testowano na klatkach H3.**

## 7. Pomiar, nie wrażenie

Zszywanie samo nie mierzy dryfu geometrii. Do tego jest `scripts/measure_scene_drift.py` (rejestracja affine na statycznych ROI, progi prowizoryczne). Zobacz [NEXT_TESTS.md](NEXT_TESTS.md), test T4.
