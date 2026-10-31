# comfyui_h3_director: węzeł „H3 Director” dla MiniMax H3 (Ref2VA)

Wtyczka do ComfyUI. Daje panel planu ujęć (oś czasu, czasy wpisywane tekstem, prompty, referencje dodawane po kolei z limitami modelu) i węzeł, który przekazuje referencje obrazów do wejść `ref_image_0..8` węzła `MiniMaxH3ReferenceToVideo`.

> **Status:** logika w Pythonie i w JS jest przetestowana bez ComfyUI (zob. sekcja „Testy”). Sama wtyczka w ComfyUI **nie jest jeszcze uruchomiona** na R9700. Zobacz [INSTALL_AND_TEST.md](INSTALL_AND_TEST.md).

## Zawartość pakietu

| Plik | Rola |
|---|---|
| `__init__.py` | rejestracja węzła (`H3Director`), `WEB_DIRECTORY = ./web` |
| `h3_director_node.py` | węzeł ComfyUI: wejście `plan_json`, wyjścia `ref_image_0..8`, `summary`, `shot_count` |
| `h3_plan.py` | logika planu (czas, klatki 17n+5, limity, walidacja, mapowanie slotów) |
| `web/h3_director.js` | rozszerzenie frontendu: przycisk „Otwórz panel” na węźle, synchronizacja planu |
| `web/h3_director_panel.html` | panel (oś czasu, ujęcia, referencje); działa też samodzielnie w przeglądarce |
| `web/plan_core.js` | ta sama logika co `h3_plan.py`, po stronie przeglądarki |
| `examples/example_plan.json` | przykładowy plan (2 ujęcia) |
| `tests/` | testy (Python i Node/Playwright), patrz niżej |

## Jak to działa

1. Otwierasz węzeł **H3 Director** w grafie i klikasz **Otwórz panel H3 Director**.
2. W panelu: ustawiasz długość utworu, dodajesz ujęcia (czas jako `12.5`, `1:02.5`, `0:01:02.5`), prompty, referencje obrazów po kolei (limit 8 lub 9, zależnie od liczby ujęć).
3. Każda zmiana w panelu przepisuje plan do pola `plan_json` węzła (przez `postMessage`). Zapisuje się wraz z workflow.
4. Węzeł zamienia plan na sloty: `ref_image_0` to pierwszy obraz z planu, `ref_image_1` drugi, itd. Puste sloty to `None`.

**Limity (z kodu `nodes_minimax_h3.py`):** 9 obrazów, 3 wideo, 3 audio na węzeł Ref2VA. Obraz ostatniej klatki poprzedniego ujęcia zajmuje jeden slot, więc przy wielu ujęciach użytkownik ma 8 obrazów.

## Czego węzeł NIE robi

- **Nie dekoduje wideo ani audio.** Referencje wideo i audio podłączasz osobnymi węzłami core: `LoadVideo` → `GetVideoComponents` (wyjście `images`) do `ref_video_N`, oraz `LoadAudio` do `ref_audio_N`. Nazwy plików są w polu `summary`.
- **Nie zmienia połączeń grafu w trakcie działania.** Podłączasz w grafie tylko używane sloty. Podłączenie pustego slotu daje błąd wykonania [UNVERIFIED w Twoim ComfyUI].
- **Nie generuje grafu Ref2VA.** Ten węzeł to źródło referencji. Resztę grafu (modele, próbkowanie, zapis) bierzesz z `workflows/` albo budujesz sam.

## Testy

Bez ComfyUI, na CPU:
```bash
python3 custom_nodes/comfyui_h3_director/tests/test_h3_plan.py
python3 custom_nodes/comfyui_h3_director/tests/test_node_logic.py
node custom_nodes/comfyui_h3_director/tests/test_plan_core.js
node custom_nodes/comfyui_h3_director/tests/test_panel_ui.js   # wymaga Playwright + Chromium
```
Wszystko naraz (razem z resztą repo): `python3 scripts/run_offline_tests.py`.

**Nie testowane automatycznie:** ładowanie obrazów przez `folder_paths` i torch (działa tylko w ComfyUI), rejestracja rozszerzenia JS w ComfyUI (zależy od wersji frontendu), wykonanie grafu na GPU. Te punkty są w [INSTALL_AND_TEST.md](INSTALL_AND_TEST.md).

## Znane ograniczenia

- Prompty są wspólne dla planu, a referencje globalne (nie per ujęcie). Różne referencje dla każdego ujęcia wymagałyby innej struktury grafu.
- Pole `plan_json` jest tekstem JSON. Ręczna edycja jest możliwa, ale błędny JSON zatrzyma węzeł z czytelnym komunikatem.
- Panel otwierany z węzła to okno przeglądarki. Blokada wyskakujących okien wyłącza przycisk.
