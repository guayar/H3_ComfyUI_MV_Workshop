#!/usr/bin/env python3
"""Wrzuca graf ComfyUI (format API) do kolejki lokalnego serwera ComfyUI.

Przyklad:
  python3 scripts/queue_shot.py workflows/h3_r2v_shot_api.json \
      --set 7.prompt="Gardener walks in, turns to the roses, no speech" \
      --set 7.length=243 --set 10.noise_seed=42 --set 14.filename_prefix=h3/shot_010

Wymaga tylko biblioteki standardowej Pythona. Serwer ComfyUI musi dzialac (domyslnie 127.0.0.1:8188).
"""
import argparse
import json
import sys
import urllib.request


def apply_override(graph, spec):
    """spec w postaci NODE.FIELD=VALUE; VALUE jest parsowane jako JSON, a w razie bledu jako tekst."""
    target, _, raw = spec.partition("=")
    node_id, _, field = target.partition(".")
    if not node_id or not field or node_id not in graph:
        sys.exit(f"Nieznany wezel w --set: {spec}")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = raw
    graph[node_id]["inputs"][field] = value


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("graph", help="sciezka do pliku JSON z grafem (format API)")
    parser.add_argument("--server", default="http://127.0.0.1:8188", help="adres serwera ComfyUI")
    parser.add_argument("--set", action="append", default=[], metavar="NODE.FIELD=VALUE",
                        help="nadpisuje wartosc wejscia wezla (mozna podac wiele razy)")
    parser.add_argument("--dry-run", action="store_true", help="tylko wypisz graf, nic nie wysylaj")
    args = parser.parse_args()

    with open(args.graph, encoding="utf-8") as fh:
        graph = json.load(fh)
    for spec in args.set:
        apply_override(graph, spec)

    if args.dry_run:
        print(json.dumps(graph, indent=2, ensure_ascii=False))
        return

    payload = json.dumps({"prompt": graph}).encode("utf-8")
    request = urllib.request.Request(f"{args.server}/prompt", data=payload,
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=60) as response:
        print(response.read().decode("utf-8"))


if __name__ == "__main__":
    main()
