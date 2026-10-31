# Instrukcja: H3 ComfyUI MV Workshop

Pełny opis, jak używać tego repo. Wersja skrócona jest w [README główny](../README.md).

> ⚠️ **Stan projektu:** workflow nie jest jeszcze zbudowany ani przetestowany. Poniższa instrukcja opisuje docelowy sposób pracy. Każdy krok oznaczony **(do weryfikacji)** wymaga potwierdzenia na sprzęcie.

---

## 1. Wymagania

**Sprzęt i system**
- Ubuntu, GPU AMD Radeon AI PRO R9700 (32 GB VRAM, gfx1201), ROCm.
- Brak zależności od CUDA. Nie używamy kerneli tylko dla CUDA (FP8 CUDA, SageAttention).

**Oprogramowanie**
- ComfyUI (wersja 0.30.0 lub nowsza, sprawdzona wersja: **(do weryfikacji)**).
- Python z zależnościami ComfyUI dla ROCm.
- `ffmpeg` do końcowego kodowania.

**Modele MiniMax H3** (źródło: Hugging Face, `Comfy-Org/MiniMax-H3`):
- `minimax_h3_ref2va_pruned_int8_convrot.safetensors` – tryb Ref2VA (referencje do wideo).
- Wariant FL2VA – tryb pierwsza/ostatnia klatka.
- Text encoder Qwen3-VL 32B oraz VAE wideo i audio H3.
- Turbo LoRA (4 i 8 kroków) oraz Fun ControlNet Union (int8).

Wagi są duże (Ref2VA int8 ok. 19,5 GB). Pobierz je przed startem.

**Węzły (custom nodes)** – każdy wymaga zgody przed instalacją:
- `tritant/ComfyUI_MiniMax_H3_Extender` (Apache-2.0) – łączenie klipów. Status: **do przeglądu kodu, nie zainstalowany**.

---

## 2. Instalacja

1. Zainstaluj ComfyUI i zweryfikuj działanie na ROCm.
2. Pobierz modele H3 do katalogów ComfyUI (`models/diffusion_models`, `models/text_encoders`, `models/vae`, `models/loras`). Ścieżki **(do weryfikacji)**.
3. Po zatwierdzeniu skopiuj węzły do `ComfyUI/custom_nodes/` i zrestartuj ComfyUI.
4. Sprawdź w przeglądarce, czy węzły H3 są widoczne i czy wczytuje się szablon `video_minimax_h3_r2v.json`.

---

## 3. Jak prowadzić projekt

Workflow dzieli pracę na etapy. Po każdym etapie następuje **bramka człowieka**: kolejny fragment startuje dopiero po zatwierdzeniu poprzedniego.

### Krok 1 – Biblia projektu i pakiet referencji
- Zdefiniuj w `projects/<nazwa>/` lokacje, postacie, rekwizyty i skalę.
- Referencje to **stałe pliki**. Model ich nie regeneruje.

### Krok 2 – Plan ujęć
- Podziel każdy fragment piosenki na możliwie najmniej generacji (cel: pojedyncze ujęcia 8–11 s, bez wydłużania).
- Każde ujęcie ma: jeden zwrot akcji, nazwaną kamerę, referencje, seed i prompt.

### Krok 3 – Sterowanie kamerą i strukturą
- Cel: zachować ten sam zestaw przy różnych ujęciach. Kandydaci: Fun ControlNet (Canny/Depth z ustawionej sceny), LoRA kamery, pierwsze/ostatnie klatki. **Nieprzetestowane.**

### Krok 4 – Generacja ujęcia
- H3 Ref2VA, rozdzielczość 1344×768, 24 fps, długość w siatce 17n+5 klatek.
- Maks. ok. 345 klatek na jedną generację (14,4 s). Dłuższe fragmenty dziel na ujęcia.
- Turbo LoRA dla szybkości.

### Krok 5 – Połączenia i cięcia
- Łączenie ujęć i cięcia na bicie. Zmiany ostrości, koloru i perspektywy na granicy muszą być niewidoczne. **Metoda do zweryfikowania.**

### Krok 6 – Post-processing
- Przywracanie ostrości (LMS LoRA w oknach po 17n+5 klatek), stabilizacja, dopasowanie tonów.
- Wyjście jako sekwencja PNG (bezstratnie).
- Jedno końcowe kodowanie ffmpeg z jawnym BT.709.

### Krok 7 – Kontrola jakości i montaż
- Automatyczne sprawdzenie każdego ujęcia (dryf, ostrość, kolor, mowa).
- Montaż z oryginalnym audio piosenki, **nie** z audio każdego klipu.

---

### Graf: `workflows/h3_r2v_shot_api.json`

Pierwszy, minimalny graf jednego ujęcia Ref2VA (format API ComfyUI). Zawiera tylko klasy potwierdzone w oficjalnym szablonie Comfy, plus `SaveImage` do sekwencji PNG.

- Wejścia: `set_plate.png` (węzeł 5, lokacja) i `character_sheet.png` (węzeł 6, postać). Pliki muszą być w folderze `input/` ComfyUI.
- Prompt: węzeł 7, pole `prompt`. Długość: pole `length` (formuła 17n+5, patrz [RESEARCH_DEEP.md](RESEARCH_DEEP.md)).
- Turbo LoRA i 4 kroki nie są w tym grafie. Domyślnie 20 kroków, bez LoRA.

**Uruchomienie** (serwer ComfyUI na `127.0.0.1:8188`):

```bash
python3 scripts/queue_shot.py workflows/h3_r2v_shot_api.json --dry-run
python3 scripts/queue_shot.py workflows/h3_r2v_shot_api.json \
    --set 7.prompt="Gardener walks in, turns to the roses, no speech" \
    --set 7.length=243 --set 14.filename_prefix=h3/shot_010
```

**Zweryfikowane w kodzie natywnym ComfyUI** (`comfy_extras/nodes_minimax_h3.py`):
- Wyjścia węzła 7: slot 0 = `positive` (warunkowanie), slot 1 = `LATENT`. Graf jest zgodny.
- Parametr `match` z szablonu to `ref_image_size` (`match` lub `max`). `match` skaluje referencje do pola klatki, `max` do 2048 px krótszego boku, co jest kilka razy wolniejsze.
- Kolejność widgetów węzła 7: `prompt`, `width`, `height`, `length`, `ref_image_size`. Graf API ma `ref_image_size: "match"`.
- Referencje obrazów: do 9 (`ref_image_0..8`), wideo do 3, audio do 3.

**Przed uruchomieniem sprawdź schemat zainstalowanej wersji** (wersja lokalna może się różnić od `master`):

```bash
curl -s http://127.0.0.1:8188/object_info/MiniMaxH3ReferenceToVideo | python3 -m json.tool | head -80
```

**Przy pierwszym uruchomieniu sprawdź:**
1. Czy `ref_image_0` i `ref_image_1` przyjmują się jako wejścia (przy autogrow mogą mieć inne nazwy w API).
2. Wyjście bez szumu i mozaiki (gfx1201, patrz RESEARCH_DEEP §7).

## 4. Kryteria akceptacji (propozycje)

| Metryka | Próg (propozycja) |
|---|---|
| Dryf perspektywy (ECC, skala) | 1,000 ± 0,002, przesunięcie ≤ 0,5 px |
| Dopasowanie szablonu na granicy | ≥ 0,99 |
| Ciągłość ostrości na granicy | zmiana ≤ 5 % |
| Ciągłość koloru (R, G, B) | zmiana ≤ 2 % |
| Ciche ujęcia | brak wykrytej mowy (Whisper) |
| Efekty fizyczne | brak czarnych dziur i rozmazanych fragmentów |

Progi są propozycją do walidacji na pierwszych testach.

---

## 5. Struktura repo

```
.
├── README.md                  # krótki opis + linki
├── docs/
│   ├── README.md              # ta instrukcja
│   └── RESEARCH_PARTIAL.md    # raport z researchu (zweryfikowane / nie)
└── (planowane)
    ├── workflows/             # pliki JSON grafów ComfyUI
    ├── projects/              # bibliotek projektów: referencje, plany ujęć
    └── scripts/               # QC, łączenie, kodowanie
```

---

## 6. Znane ograniczenia

- Ruchoma kamera w H3 jest niewiarygodna bez dodatkowego sterowania. Potrzebny test.
- H3 generuje audio i animuje usta, nawet gdy postać ma milczeć. Wyciszenie nie jest jeszcze sprawdzone.
- Dłuższe łańcuchy klipów kumulują dryf. Przy łańcuchach powyżej 3–4 klipów jakość spada.
- Część informacji z zewnętrznych źródeł pochodzi od stron trzecich i wymaga potwierdzenia (szczegóły w [RESEARCH_PARTIAL.md](RESEARCH_PARTIAL.md)).

---

## 7. Co dalej

1. Zatwierdzić instalację i przegląd kodu `ComfyUI_MiniMax_H3_Extender`.
2. Pobrać modele i przetestować Ref2VA na jednym krótkim ujęciu.
3. Zmierzyć dryf i ostrość na granicy dwóch ujęć.
4. Dopiero potem rozwijać resztę workflow.

Opis każdego kroku zapisuj w `docs/` jako nową sekcję, a nie w głównym README.
