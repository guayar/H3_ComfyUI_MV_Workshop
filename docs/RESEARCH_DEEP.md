# Głęboki research: rozwiązania dla problemów H3

Stan: research z rozszerzonym wyszukiwaniem i odczytem README. Każda teza ma status: **[ZWERYFIKOWANE]** (potwierdzone w oficjalnym szablonie lub kodzie/README), **[DEKLAROWANE]** (autor twierdzi, brak pomiaru), **[NIEZWERYFIKOWANE]** (brak źródła lub źródło niedostępne).

Zablokowane w sesji: `docs.comfy.org`, `www.runcomfy.com`. Dane z nich pochodzą z wyników wyszukiwania, nie z odczytu strony.

## 1. Nazwy węzłów i modele (ZWERYFIKOWANE)

Źródło: oficjalny szablon Comfy `video_minimax_h3_r2v.json` (repo `Comfy-Org/workflow_templates`, odczyt raw JSON).

Klasy użyte w grafie `workflows/h3_r2v_shot_api.json`:

| Klasa | Rola |
|---|---|
| `UNETLoader` | model `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| `CLIPLoader` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors`, typ `minimax` |
| `VAELoader` | `minimax_h3_video_vae_int8_convrot.safetensors`; `minimax_h3_audio_vae_fp32.safetensors` |
| `MiniMaxH3ReferenceToVideo` | Ref2VA: `clip`, `vae`, `audio_vae`, `ref_image_0..2`, `ref_video_0`, `ref_video_audio_0`, `ref_audio_0`, `prompt`, `width`, `height`, `length` |
| `LoraLoaderModelOnly` | turbo `minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors` |
| `BasicScheduler`, `KSamplerSelect`, `RandomNoise`, `BasicGuider`, `SamplerCustomAdvanced` | próbkowanie (`res_multistep`, scheduler `simple`, 20 kroków w szablonie) |
| `VAEDecode`, `VAEDecodeAudio`, `CreateVideo`, `SaveVideo` | dekodowanie i zapis (szablon używa `SaveVideo`) |

Formuła długości z szablonu (`ComfyMathExpression`): dla czasu `a` w sekundach `max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17`. Daje klatki w siatce 17n+5. Przykłady: 5 s → 124, 8 s → 192, 10 s → 243.

**Uwagi o szablonie:**
- Szablon używa `SaveVideo`. Według briefu `SaveVideo` przesuwa kolory (BT.601 vs BT.709), dlatego graf zapisuje PNG (`SaveImage`), a kodowanie robimy osobno ffmpeg.
- **[ZWERYFIKOWANE w kodzie]** Szósty parametr szablonu `"match"` to widget `ref_image_size` (`match` | `max`). Graf ma go ustawiony na `match`.
- **[ZWERYFIKOWANE w kodzie]** Wyjścia `MiniMaxH3ReferenceToVideo`: slot 0 = `positive` (CONDITIONING), slot 1 = `LATENT`. Graf jest zgodny.
- **[ZWERYFIKOWANE w kodzie]** Wejścia: `clip`, `vae` (opcjonalne, bez niego referencje obrazów działają tylko na enkoder tekstu), `audio_vae`, `prompt`, `width`, `height`, `length` (krok 17), `ref_image_size`, autogrow `ref_images` (0–9), `ref_videos` (0–3), `ref_video_audios` (0–3), `ref_audios` (0–3). Źródło: https://raw.githubusercontent.com/Comfy-Org/ComfyUI/master/comfy_extras/nodes_minimax_h3.py
- Węzły `SaveImage`, `LoadImage`, `VAEDecode`, `BasicScheduler` itd. to węzły rdzenia ComfyUI. Ich nazwy są standardowe.

## 2. Kamera (problem #1)

- **[DEKLAROWANE]** Orbit 360° LoRA dla FL2VA (`pablodawson/MiniMax-H3-360-Orbit-LoRA`). Model-only, bez custom nodes, siła 1.0, trenowany na 28 renderach. Autor twierdzi, że kamera wraca do pozycji startowej, czego baza nie robi. Źródło: https://huggingface.co/pablodawson/MiniMax-H3-360-Orbit-LoRA
- **[DEKLAROWANE]** Wariant Ref2VA z orbitą i dodatkowym card-spin (rank 32): https://huggingface.co/MATLOWAI/MiniMax-H3-ORB360-CardSpin
- **[DEKLAROWANE]** Camera Motion LoRA z edytorem (azymut, elewacja, dystans) i opisem orbit/dolly/tilt. Brak pomiarów. Źródło (strona blokowana w sesji, tylko wynik wyszukiwania): runcomfy.com.
- **[DEKLAROWANE]** Eksperymentalne LoRA z innego zbioru: wynik silnie zależy od klipu, rozdzielczości i promptu. Styl-transfer LoRA daje mniej przewidywalną kamerę. Źródło: https://huggingface.co/daniel042310/Minimax-H3-ComfyUI
- **Brak** źródła z zmierzoną dokładnością kamery (dolly, crane). Plan testu z briefu jest nadal potrzebny.

**Rekomendacja:** test orbity LoRA na jednym ujęciu, potem pomiar ECC. Dolly i crane wymagają własnego testu.

## 3. Spójność długich sekwencji / wiele ujęć (problem #2 i #4)

- **[DEKLAROWANE, kod istnieje]** `tritant/ComfyUI_MiniMax_H3_Extender` (Apache-2.0). README potwierdza:
  - węzły: `MiniMax H3 Extender`, `MiniMax H3 Reference Pack Bridge`, `MiniMax H3 Prompt Pack Bridge`, `Final Decode / Preview` (natywny wyjście `VIDEO`), `Motion Context Disk Join` (przestarzały);
  - do 9 obrazów, 3 wideo i 3 audio referencji globalnie;
  - wejście wideo wyrównywane do siatki 17k+5, 24 fps;
  - zmiana parametru unieważnia klip i wszystkie późniejsze;
  - w wersji 2.9.0 ostatnie klatki klipu 0 są kontekstem wizualnym dla pierwszego wygenerowanego klipu, z opcją „Choose Ref”;
  - opcjonalne dopasowanie kolorów do obrazu referencyjnego (przestrzeń LAB, blend 0.0–1.0).
  - Nazw klas i domyślnych wartości README nie podaje. **[NIEZWERYFIKOWANE]** Plik `node.py` i `__init__.py` wymagają odczytu kodu.
  - Repo: https://github.com/tritant/ComfyUI_MiniMax_H3_Extender
- **[DEKLAROWANE]** `SatoDive/Minimax-H3-Latent-Continuation`: przekazywanie latentów między ujęciami. Autor deklaruje „100% visual context consistency”, ale to marketing bez pomiarów. Część wieloujęciowa to roadmapa. https://github.com/SatoDive/Minimax-H3-Latent-Continuation
- **[ZWERYFIKOWANE jako istnienie]** `vizart-vj/ComfyUI-MiniMax-H3-LongMedia`: węzły `h3_latent_upscaler.py`, `latent_relay.py`, `stitch_continuation.py`. Issue #28 opisuje błąd: cicha ścieżka audio w jednym segmencie psuje audio i lip-sync całej sekwencji. https://github.com/vizart-vj/ComfyUI-MiniMax-H3-LongMedia/issues/28
- **Brak** źródła dla współdzielonego przebiegu odszumiania (shared denoising) ani dla context windows wewnątrz H3. Pytanie 3 z briefu pozostaje otwarte.

**Rekomendacja:** traktować Extender jako punkt startu do testu, nie jako rozwiązanie dryfu. Sprawdzić jego wpływ na geometrię zestawu metryką z briefu.

## 4. Wyciszenie mowy i lip-sync (problem #5)

- **[ZWERYFIKOWANE w dokumentacji ComfyUI]** Audio jest zawsze generowane razem z wideo (stereo, jeden przebieg). Brak opcji wyłączenia w znalezionych źródłach.
- **[ZWERYFIKOWANE w dokumentacji ComfyUI]** Referencja audio wymaga co najmniej jednej referencji obrazu lub wideo.
- **[ZWERYFIKOWANE w issue #28]** Cicha referencja audio psuje synchronizację. Obejście: dodać cichy ambient do referencji, żeby żaden jej fragment nie był całkowicie cichy.
- **[DEKLAROWANE]** Prompt w stylu „No additional speech, ambience…” zadziałał w jednym workflow. Nie potwierdzone pomiarem.
- **Wniosek:** samo wycięcie ścieżki audio (`ffmpeg -an`) nie usuwa ruchu ust. Trzeba mierzyć ruch w obszarze ust i Whisperem. **[NIEZWERYFIKOWANE]** czy istnieje mute w węźle.

## 5. Efekty fizyczne i zmiany scenerii (problem #6)

- **Brak** źródła dla maskowania ani control video do efektów typu klapy podłogi. Plan testu: maska + Fun ControlNet inpainting (patrz §6).

## 6. Fun ControlNet (problem #2)

- **[ZWERYFIKOWANE w wyniku wyszukiwania, odczyt strony zablokowany]** Fun ControlNet Union patch obsługuje Canny, Depth, HED, MLSD, Pose oraz inpainting wideo z maską. Działa z `fl2va` i `ref2va`. Kontrolka przycinana do długości celu; krótsza trzyma ostatnią klatkę. Źródło: https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fun-controlnet (blokowane w tej sesji, tylko snippet).
- **[NIEZWERYFIKOWANE]** Nazwa klasy węzła ControlNet (w repo `ComfyUI-H3-FunControl`, węzeł `H3 Fun Control Apply` wg strony RunComfy). Nie wpisałem jej do grafu, bo nie mam potwierdzenia.
- **Brak** potwierdzonych wartości siły i zakresu start/end percent dla ControlNet w Ref2VA.

## 7. Speed i ROCm na gfx1201 (problem #7)

- **[ZWERYFIKOWANE]** ROCm/aiter PR #6066 dodaje operatory gfx1201 dla wielu GPU H3 (Ulysses SP2/4/8): https://github.com/ROCm/aiter/pull/6066
- **[ZWERYFIKOWANE]** Community patch `charlie12345/R9700AIProComfyUIPatch` dla RDNA4 R9700 (Windows): wymaga `comfy-kitchen` 0.2.26+, a `torch._int_mm` jest w nim zepsute na gfx1201. https://github.com/charlie12345/R9700AIProComfyUIPatch
- **[ZWERYFIKOWANE]** Issue ComfyUI #15314: szum/mozaika na RX 7900 XTX (gfx1100) z oficjalnym szablonem, ROCm 7.2.4. Nie gfx1201, ale ten sam wzorzec błędu. https://github.com/Comfy-Org/ComfyUI/issues/15314
- **[ZWERYFIKOWANE]** Zgłoszenie z RX 9070 XT (gfx1201) na Linuxie działa z `HSA_OVERRIDE_GFX_VERSION`. https://huggingface.co/Comfy-Org/MiniMax-H3/discussions/17

**Wniosek:** przy pierwszym uruchomieniu sprawdzić, czy wyjście nie jest zaszumione lub zmozaikowane (wzorzec z #15314), i zweryfikować `torch._int_mm`.

## 8. Licencja (do sprawdzenia przed użyciem komercyjnym)

- **[NIEZWERYFIKOWANE, sprzeczne źródła]** Jedno źródło mówi, że otwarte wagi H3 mają licencję terytorialną wykluczającą USA, UE, UK i Koreę Południową. Nie potwierdziłem tego w źródle MiniMax. Przed użyciem komercyjnym sprawdzić dokładną licencję modelu.

## 9. Co wymaga zgody przed instalacją

- `tritant/ComfyUI_MiniMax_H3_Extender` – odczyt kodu, potem instalacja.
- Pozostałe repo (`SatoDive`, `vizart-vj`, LoRA od stron trzecich) – tylko do przeglądu, bez instalacji.

## 10. Otwarte pytania (w kolejności testów)

1. Kolejność wyjść `MiniMaxH3ReferenceToVideo` (test: uruchomić graf i sprawdzić błąd lub wynik).
2. Nazwa parametru `match` w `MiniMaxH3ReferenceToVideo`.
3. Orbit LoRA: dokładność kamery mierzona ECC.
4. ControlNet przez granicę ujęć: czy zachowuje geometrię zestawu (metryka skali i przesunięcia).
5. Wyciszenie ruchu ust bez audio.
6. Szum/mozaika na gfx1201.

## 11. Addendum (2026-10-31): co zweryfikowano i co przejęto

Źródła poniżej podał kolejny raport. Oznaczenia: **[KOD]** przeczytany w kodzie, **[ISSUE]** zgłoszenie użytkownika, **[DEKLARACJA]** autor bez niezależnego pomiaru, **[NIEZWERYFIKOWANE]** nie opierać na tym produkcji.

- **[KOD] Native Fun ControlNet** (`MiniMaxH3FunControlNetApply`, ten sam plik `nodes_minimax_h3.py`): wejścia `model`, `model_patch` (MODEL_PATCH), `vae`, `strength` (1.0, 0–10), `start_percent` (0.0), `end_percent` (1.0), opcjonalnie `control_video` (IMAGE), `mask` (1 = do wygenerowania), `source_video` (tło pod maską). Wyjście: MODEL. **Loadera `model_patch` nie ma w tym pliku**, trzeba go znaleźć w `/object_info`.
- **[KOD] Extender `tritant`** (wersja w `main` to 3.0.14, lokalnie 3.0.12): klasy `MiniMaxH3Extender` (wyświetlana: „MiniMax H3 Extender”), `MiniMaxH3ReferencePackBridge`, `MiniMaxH3TailFromLatent`. Domyślne wartości głównego węzła: `run_mode` clip_by_clip, `width` 896, `height` 576, `ref_image_size` match, `steps` 4, `denoise` 1.0, `context_length` "22", `generation_mode` ref2va, `motion_context` True, `refine_enabled` False. Brak dedykowanego wejścia ControlNet. Wejście `continue_existing_video` musi być natywnym VIDEO (np. Load Video), nie batchem klatek.
- **[KOD] Shared denoising istnieje:** `Jalen-Brunson/ComfyUI-HybridWindows` (`H3HybridWindows`, `MMH3HybridWindowSampler`, `H3HybridControlNet`). Dwufazowy sampler: sekwencyjne rozgrzewanie okien, potem wspólny ogon na jednej osi czasu latentów. Domyślnie `sequential_steps=6`, `overlap_pin=full`. Wymaga MMH3Tools. **[DEKLARACJA]** poprawa dryfu w testach autora, nie zmierzona na R9700.
- **[DEKLARACJA] Orbit LoRA** (`pablodawson`): FL2VA, 768×768, 73 klatki, 28 kroków, siła 1.0, trenowany na 28 orbitach. Brak niezależnego pomiaru kąta lub dryfu. Precyzyjnego dolly nie sprawdzono.
- **[ISSUE] Audio/usta:** `vizart-vj/ComfyUI-MiniMax-H3-LongMedia#28`: cisza cyfrowa w pierwszych 5 s referencji lip-sync psuje dalszą mowę i audio; dodanie cichego ambientu to naprawiło u zgłaszającego. Brak natywnego `mute_lips` ani `disable_audio`. Usunięcie ścieżki audio nie usuwa ruchu ust.
- **[ISSUE] ROCm:** `Comfy-Org/ComfyUI#15314` dotyczy gfx1100 (RX 7900 XTX), nie gfx1201. `ROCm/aiter#6066` to multi-GPU na gfx1201, bez poprawki dla pojedynczej karty. Patch `charlie12345` to Windows, nie stosować na Linux ROCm bez testu.
- **[NIEZWERYFIKOWANE] Efekty fizyczne** (klapy podłogi): H3 może nie zinterpretować kontroli Canny/depth jako dokładnej fizyki klap. Wymaga testu.

**Zasady z addendum, które obowiązują:** nie instalować ani nie aktualizować wtyczek bez przeglądu; porównać `/object_info` z kodem przed każdą zmianą; nie zakładać, że wersja z `master` jest tą lokalną; prompty pozytywne, jeden nazwany ruch kamery lub zablokowany statyw.


## 12. Addendum (handoff, 2026-10-31): ustalenia z briefu i ich status

Etykiety: `[CODE]` sprawdzone w kodzie, `[AUTHOR]` deklaracja autora lub karta modelu, `[USER REPORT]` zgłoszenie, `[UNVERIFIED]` nieprzetestowane na tej maszynie. Źródła nie były pobierane ponownie w tej sesji (huggingface.co i docs.comfy.org są zablokowane), więc poniższe wpisy pochodzą z briefu.

### 12.1 Natywny Ref2VA [CODE]
- Źródło: https://github.com/Comfy-Org/ComfyUI/blob/master/comfy_extras/nodes_minimax_h3.py
- `MiniMaxH3ReferenceToVideo`: wyjście 0 = `positive` (CONDITIONING), wyjście 1 = LATENT.
- `ref_image_size` (`match` | `max`, domyślnie `match`). `max` zachowuje więcej tokenów referencji i może być wielokrotnie wolniejszy.
- Do 9 obrazów, 3 wideo, 3 audio. Bez VAE wideo referencje obrazów działają tylko na enkoder tekstu.
- Klatki `17n+5` przy 24 fps. `MiniMaxH3AddGuide` przyjmuje `frame_idx` względem pełnej osi czasu.
- **Schemat zainstalowanej wersji może się różnić od upstream.** Sprawdź `/object_info` przed każdym grafem (`scripts/audit_h3_runtime.py`).

### 12.2 Fun ControlNet: plik i węzeł
- Lista oficjalnych plików: https://huggingface.co/Comfy-Org/MiniMax-H3/tree/main/model_patches [AUTHOR, nie pobrane tutaj]
- Przykład oficjalny: https://github.com/Comfy-Org/workflow_templates/blob/main/templates/video_minimax_h3_fun_controlnet_union.json [AUTHOR]
- **Potwierdzone w oficjalnym szablonie (odczyt JSON z GitHuba, węzeł 173 `ModelPatchLoader`):** `minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors`; węzeł 172 `MiniMaxH3FunControlNetApply`: strength 1, start 0, end 1. Szablon steruje pozą przez podgraf SDPose (`sdpose_wholebody_fp16.safetensors`, `rt_detr_v4-x-hgnet_fp16.safetensors`), a nie przez Canny. Nie kopiować tego bez decyzji: to inne źródło sterowania. [CODE szablonu, nie uruchomione]
- **Kandydat do `ModelPatchLoader.name` (wcześniejszy zapis):** `minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors`. Pozostali: `..._pruned_bf16`, `union_2.0_pruned_int8_convrot`, `union_2.0_pruned_bf16`. Każdy wymaga potwierdzenia audytem; nie podstawiać nazwy bez potwierdzenia.
- Węzeł `MiniMaxH3FunControlNetApply` [CODE]: `model`, `model_patch`, `vae`, `strength` (1.0, 0–10), `start_percent` (0), `end_percent` (1), `control_video` (IMAGE, opcj.), `mask` (MASK, >0.5 = regeneruj), `source_video` (IMAGE, opcj.). Wyjście MODEL.
- Klatki sterujące i maski są indeksowane po klatkach generacji; krótsze są powtarzane ostatnią klatką [CODE].
- **Statyczna krawędź Canny nie steruje podnoszeniem klap.** Do tego potrzebne jest sterowanie klatka po klatce (`scripts/make_control.py --flap-demo`) [CODE w naszym skrypcie; zachowanie H3 UNVERIFIED].
- Demo inpaint [AUTHOR]: https://huggingface.co/alibaba-pai/MiniMax-H3-Fun-Controlnet-Union-2.0 (`asset/inpaint_mask.mp4`). Istnienie demo nie dowodzi fizyki ani zgodności z AMD.
- Osobna implementacja `H3FunControlApply` (https://github.com/wyzborrero/ComfyUI-H3-FunControl) ma inny zakres siły i inne wymagania checkpointu. **Nie mieszać nazw klas.** Najpierw natywna.

### 12.3 Kodowanie tekstu, ROCm [CODE + AUTHOR]
- Wagi: https://huggingface.co/SearchingMan/MiniMax-H3-Text-Encoders [AUTHOR]
- Loader: https://github.com/kgonia/ComfyUI-MiniMaxH3TextEncoders [CODE]. Węzeł `MiniMaxH3TextEncoderLoader` zwraca CLIP i stosuje logikę pruned + adapter. **Zwykła podmiana nazwy pliku w `CLIPLoader` nie jest równoważna.**
- Kandydat: pakiet `pruned24_balanced` (INT8 ConvRot) z manifestem i adapterem ARA. Nie wrzucać samego pliku safetensors do domyślnego loadera.
- **Nie używać `recovered_8b_int8_convrot` dla Ref2VA.** Tokenizer rzuca wyjątek, gdy podano `images` lub `minimax_ref_items`, bo jest tylko T2V. Patrz `RecoveredMiniMaxTokenizer.tokenize_with_weights` w `__init__.py` tego loadera [CODE].
- Podobieństwo kondycjonowania i VRAM od autora to [AUTHOR], nie pomiar na R9700.
- Zanim zastąpisz działający enkoder NVFP4, ustal, czy NVFP4 **faktycznie** zawodzi lokalnie. Jeśli działa, zachowaj go jako baseline. Nowy enkoder testuj z tym samym seedem, referencjami, modelem, samplerem i promptem.

### 12.4 `torch._int_mm` na gfx1201 [UNVERIFIED]
- Nie przenosić wniosków z gfx1100: https://github.com/Comfy-Org/ComfyUI/issues/15314
- `ROCm/aiter#6066` dotyczy głównie operatorów multi-GPU H3, nie dowodzi działania ani awarii INT8 na jednej karcie: https://github.com/ROCm/aiter/pull/6066
- Patch dla R9700 jest pisany pod Windows i nie dowodzi poprawności na Linux ROCm.
- Test: `scripts/int8_mm_microtest.py` (osobny proces, porównanie z int32 na CPU, zapis wersji i wyjątków). **Nie uruchomiony:** brak torch w tym środowisku.

### 12.5 H3 Extender [CODE], gałąź opcjonalna
- Źródło: https://github.com/tritant/ComfyUI_MiniMax_H3_Extender/blob/main/extender.py. Wersja `main` to 3.0.14; lokalnie podawano 3.0.12. Porównaj przed użyciem.
- Klasa `MiniMaxH3Extender`, `FUNCTION=extend`. Domyślne: `run_mode=clip_by_clip`, `width=896`, `height=576`, `steps=4`, `sampler_name=euler`, `scheduler=simple`, `context_length="22"`, `motion_context=True`, `generation_mode=ref2va`, `ref_image_size=match`, `refine_enabled=False`, `refine_denoise=0.30`.
- `continue_existing_video` musi być natywnym VIDEO (np. Load Video). Jego ogon jest dekodowany i ponownie kodowany VAE.
- Węzeł przyjmuje łatany MODEL, więc typ jest zgodny z natywnym Fun ControlNet. Wykonanie i poprawa dryfu: UNVERIFIED.
- **Nie czyni go domyślną ścieżką.**

### 12.6 HybridWindows [CODE], benchmark eksperymentalny
- https://github.com/Jalen-Brunson/ComfyUI-HybridWindows (`nodes.py`, `sampler.py`, `control.py`).
- Klasy: `H3HybridWindows`, `MMH3HybridWindowSampler`, `H3HybridControlNet`.
- Sekwencyjne rozgrzewanie okien, potem wspólne okna nakładające się na jednej osi latentów. Nie jest to zwykłe crossfade po dekodowaniu.
- `sequential_steps` domyślnie 6. Przy 8 krokach: 6 sekwencyjnych + 2 wspólne. `overlap_pin` domyślnie `full`, dostępny `tail_custom`.
- Wymaga MMH3Tools. Nieprzetestowane na R9700. **Poza główną ścieżką grafu.**

### 12.7 Audio i usta [CODE / USER REPORT]
- H3 sprzęga wideo i audio. Usunięcie ścieżki z MP4 nie zatrzymuje ruchu ust.
- Brak natywnego `mute_lips` ani `disable_audio` w znalezionym kodzie [CODE].
- Zgłoszenie o cichej referencji audio: https://github.com/vizart-vj/ComfyUI-MiniMax-H3-LongMedia/issues/28 [USER REPORT, jeden przypadek, nie ogólne rozwiązanie].
- Prompt pozytywny [AUTHOR, nie gwarantowane]: „The gardener watches the roses with relaxed closed lips; the ambient stage contains soft room tone and rustling leaves.”
- Mitigacja, nie rozwiązana funkcja: mierz obszar ust i uruchamiaj VAD/ASR na wyjściu audio. Wybieraj kadry, w których ruch ust jest mało ważny.
