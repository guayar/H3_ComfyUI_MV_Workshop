# H3 ComfyUI MV Workshop

Ogólny, wielokrotnego użytku workflow do tworzenia długich, spójnych teledysków AI z **MiniMax H3** w **ComfyUI**. Działa lokalnie na Ubuntu z AMD ROCm (jedna karta Radeon AI PRO R9700, 32 GB VRAM).

Każdy projekt dostarcza własne referencje postaci i lokacji, plan ujęć oraz styl. Projekt „Once Upon a Garden” służy jako pierwszy przypadek testowy, a nie jako wzór na sztywno.

## Status

🟡 **Faza researchu i projektowania.** Workflow jeszcze nie istnieje. Jest częściowy raport z zweryfikowanymi i niezweryfikowanymi tezami.

## Dokumentacja

- 📖 **[Instrukcja użycia i szczegóły – docs/README.md](docs/README.md)** – wymagania, instalacja, struktura projektu, jak prowadzić projekt krok po kroku.
- 🔬 **[Głęboki research – docs/RESEARCH_DEEP.md](docs/RESEARCH_DEEP.md)** – rozwiązania dla kamery, spójności, audio i ROCm, z oznaczeniem, co jest zweryfikowane.
- 🔬 **[Wstępny research – docs/RESEARCH_PARTIAL.md](docs/RESEARCH_PARTIAL.md)** – pierwsza runda.

## Jak używać w ComfyUI

- 🖱️ **[Instrukcja obsługi w UI – docs/HOW_TO_USE_UI.md](docs/HOW_TO_USE_UI.md)**: które grafy otworzyć, co wpisać, gdzie są wyniki, jak zszyć.
- 🎛️ **Panel H3 Director – `panel/h3_director_panel.html`**: plan ujęć z osią czasu, czasy wpisywane tekstem, referencje dodawane progresywnie z limitami; eksport `plan.json`.

## Graf

- `workflows/h3_r2v_shot_api.json` – minimalny graf jednego ujęcia Ref2VA (14 węzłów, format API ComfyUI).
- `scripts/queue_shot.py` – wrzuca graf do kolejki ComfyUI i pozwala nadpisać parametry.
