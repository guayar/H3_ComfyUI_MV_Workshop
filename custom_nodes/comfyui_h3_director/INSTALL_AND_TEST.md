# H3 Director: instalacja i test krok po kroku

Ten dokument jest listą kontrolną do przetestowania wtyczki na R9700. Każdy krok ma **oczekiwany wynik**. Jeśli wynik się nie zgadza, zapisz komunikat i wróć do sekcji „Gdy coś nie działa”.

## Część A: testy bez ComfyUI (5 min)

Na maszynie z repo, w katalogu `h3_comfyui_mv_workshop`:

| Krok | Polecenie | Oczekiwany wynik |
|---|---|---|
| A1 | `python3 custom_nodes/comfyui_h3_director/tests/test_h3_plan.py` | 6× `OK`, na końcu „Wszystkie testy h3_plan OK” |
| A2 | `python3 custom_nodes/comfyui_h3_director/tests/test_node_logic.py` | 6× `OK`, na końcu „Wszystkie testy wezla OK” |
| A3 | `node custom_nodes/comfyui_h3_director/tests/test_plan_core.js` | „Wszystkie testy logiki panelu OK” |
| A4 | `node custom_nodes/comfyui_h3_director/tests/test_panel_ui.js` | 8× `OK` (wymaga `npm i playwright` w środowisku z Chromium) |

Jeśli A4 nie działa z powodu braku przeglądarki, pomiń: A1–A3 testują logikę, a A4 interfejs.

## Część B: instalacja w ComfyUI

| Krok | Co zrobić | Oczekiwany wynik |
|---|---|---|
| B1 | Skopiuj katalog `custom_nodes/comfyui_h3_director` do `ComfyUI/custom_nodes/` | w `ComfyUI/custom_nodes/comfyui_h3_director/` jest `__init__.py` i `web/` |
| B2 | Uruchom ComfyUI, w konsoli serwera szukaj błędów przy starcie | brak linii `Import failed` dla `comfyui_h3_director` |
| B3 | Dodaj węzeł: dwuklik na kanwie, wpisz „H3 Director” | węzeł „H3 Director (plan + referencje)” z wejściem `plan_json` i 11 wyjściami (9 × ref_image, summary, shot_count) |
| B4 | Na węźle powinien być przycisk **Otwórz panel H3 Director** | przycisk widoczny. **Jeśli nie ma: patrz „Gdy coś nie działa”, punkt 1** |
| B5 | Kliknij przycisk | otwiera się okno z panelem (pozwól na wyskakujące okna dla strony) |

## Część C: plan z panelu do węzła

| Krok | Co zrobić | Oczekiwany wynik |
|---|---|---|
| C1 | W panelu: długość `248.76`, **+ dodaj ujęcie** | w tabeli 1 wiersz, w osi czasu 1 pasek |
| C2 | Start `0`, koniec `5.17` | „124 kl.” w kolumnie Klatki |
| C3 | Drugie ujęcie: start `5.17`, koniec `0:15.3` | „243 kl.” |
| C4 | Wpisz prompt przy każdym ujęciu | komunikat „Plan poprawny: 2 ujęć…” |
| C5 | W sekcji Referencje, Obrazy: wpisz `set_plate.png`, **Dodaj** | licznik `1 / 8`. Pozycja pojawia się na liście |
| C6 | Zamknij panel i sprawdź węzeł | w polu `plan_json` jest JSON z dwoma ujęciami (widoczny po rozwinięciu węzła) |
| C7 | Otwórz panel ponownie z węzła | panel wczytuje ujęcia z węzła, status „Wczytano plan z wezla ComfyUI” |

## Część D: wyjścia węzła w grafie

| Krok | Co zrobić | Oczekiwany wynik |
|---|---|---|
| D1 | Podłącz `ref_image_0` (wyjście węzła) do wejścia `ref_image_0` węzła `MiniMaxH3ReferenceToVideo` | połączenie niebieskie/kolorowe, bez czerwonego podkreślenia |
| D2 | Uruchom kolejkę z wczytanym obrazem `set_plate.png` w `input/` | węzeł H3Director wykonuje się bez błędu, w `summary` widać ujęcia i pliki |
| D3 | Odłącz i sprawdź `summary` (zakładka lub podgląd tekstu) | pole `summary` zawiera „ujec: 2” i nazwy plików |

## Część E: co dalej

Po części D wygeneruj Ref2VA w pełnym grafie (`workflows/h3_chain_ui.json`), używając `ref_image_0..` z węzła H3 Director zamiast wczytywania plików ręcznie. Ten krok nie jest jeszcze opisany jako gotowy graf: to następny etap.

## Gdy coś nie działa

1. **Brak przycisku na węźle.** Otwórz konsolę przeglądarki (F12). Szukaj błędu importu `app.js` lub `H3.Director`. Najczęstsza przyczyna: inna wersja frontendu ComfyUI zmienia ścieżkę `../../scripts/app.js`. Zgłoś treść błędu, poprawka jest w `web/h3_director.js`.
2. **Panel nie synchronizuje planu.** Sprawdź, czy okno panelu jest otwarte z przycisku (nie ręcznie). Ręczne otwarcie działa jako samodzielny panel, ale bez zapisu do węzła.
3. **Węzeł zgłasza „pusty plan”.** Pole `plan_json` ma wartość `{}`. Otwórz panel i zrób zmianę, żeby plan się przepisał.
4. **Węzeł zgłasza błąd limitu lub klatek.** Plan jest niezgodny z limitami. Komunikat mówi, która reguła. Popraw w panelu.
5. **`ModuleNotFoundError` przy starcie.** Sprawdź, czy skopiowano cały katalog z `__init__.py` (nie tylko pliki w środku).
6. **Obraz nie wczytuje się.** Plik musi być w `ComfyUI/input/`, a nazwa w panelu musi być dokładnie taka sama (wielkość liter też).

## Co zgłosić, jeśli test się nie uda

- Wersja ComfyUI (`GET /system_stats` → `comfyui_version`).
- Treść błędu z konsoli serwera i przeglądarki.
- Numer kroku z tego dokumentu.
