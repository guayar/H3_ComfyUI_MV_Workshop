#!/usr/bin/env python3
"""Walidacja grafu ComfyUI BEZ uruchamiania serwera, na zapisanym schemacie /object_info.

Schemat zapisujesz raz, gdy ComfyUI dziala:
  curl -s http://127.0.0.1:8188/object_info > object_info.json

Potem walidacja dziala offline:
  python3 scripts/validate_graph_offline.py workflows/h3_chain_ui.json --schema object_info.json

Sprawdza (format UI i API):
  * czy klasa wezla istnieje w schemacie                         -> MISSING_NODE
  * czy slot wyjscia istnieje i ma typ zgodny z linkiem           -> BAD_OUTPUT_SLOT / TYPE_MISMATCH
  * czy wejscie docelowe ma typ zgodny z linkiem                  -> TYPE_MISMATCH
  * czy wartosc listy wyboru (COMBO) jest dozwolona               -> COMBO_VALUE_NOT_ALLOWED
    (to lapie brakujacy plik modelu albo brakujacy plik wejsciowy)
  * czy liczby mieszcza sie w zakresie min/max                    -> RANGE
  * czy wymagane wejscia (nie-widget) sa podlaczone               -> MISSING_LINK
  * czy liczba wartosci widgets_values zgadza sie (format UI)     -> WIDGET_COUNT

Ograniczenia [UNVERIFIED]: w formacie UI kolejnosc widgets_values jest przyjeta jak w schemacie
(wymagane, potem opcjonalne). Autogrow (ref_image_N) nie ma stalej nazwy w schemacie: wejscia spoza
schematu sa tylko ostrzezeniem. Wynik walidacji to dowod zgodnosci ze schematem, nie dowod dzialania.

Kody wyjscia: 0 = brak bledow, 1 = bledy, 2 = zly plik wejsciowy.
"""
import argparse
import json
import sys

WIDGET_TYPES = {"INT", "FLOAT", "STRING", "BOOLEAN"}


def spec_info(spec):
    """Zwraca (typ, opcje_lub_None, meta_dict) dla wejscia ze schematu."""
    if not isinstance(spec, list) or not spec:
        return "?", None, {}
    first = spec[0]
    meta = spec[1] if len(spec) > 1 and isinstance(spec[1], dict) else {}
    if isinstance(first, list):
        return "COMBO", first, meta
    return first, None, meta


def ordered_inputs(schema):
    """Wejscia w kolejnosci: wymagane, potem opcjonalne (jak w ComfyUI)."""
    out = []
    for section, required in (("required", True), ("optional", False)):
        for name, spec in (schema.get("input", {}).get(section, {}) or {}).items():
            typ, opts, meta = spec_info(spec)
            out.append({"name": name, "required": required, "type": typ, "options": opts, "meta": meta})
    return out


def check_value(err, where, inp, value):
    if inp["type"] == "COMBO" and inp["options"] is not None:
        if value not in inp["options"]:
            err("COMBO_VALUE_NOT_ALLOWED", where,
                f"{value!r} nie jest na liscie dozwolonych ({len(inp['options'])} pozycji)")
    if inp["type"] in ("INT", "FLOAT") and isinstance(value, (int, float)) and not isinstance(value, bool):
        lo, hi = inp["meta"].get("min"), inp["meta"].get("max")
        if (lo is not None and value < lo) or (hi is not None and value > hi):
            err("RANGE", where, f"{value} poza zakresem [{lo}, {hi}]")


def validate_ui(graph, schema):
    errors, warnings = [], []

    def err(code, where, msg):
        errors.append({"code": code, "where": where, "message": msg})

    def warn(code, where, msg):
        warnings.append({"code": code, "where": where, "message": msg})

    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    for n in nodes.values():
        where = f"node {n['id']} {n['type']} ({n.get('title', '')})"
        sch = schema.get(n["type"])
        if sch is None:
            err("MISSING_NODE", where, f"klasa {n['type']} nie istnieje w schemacie")
            continue
        inputs = ordered_inputs(sch)
        by_name = {i["name"]: i for i in inputs}
        linked = {x["name"]: x for x in n.get("inputs", []) if x.get("link") is not None}
        # wejscia podlaczone: nazwa musi istniec w schemacie (autogrow: ostrzezenie)
        for name in n.get("inputs", []):
            nm = name["name"]
            if nm not in by_name:
                if nm.startswith("ref_"):
                    warn("AUTOGROW_UNCHECKED", where, f"wejscie {nm} nie ma stalej nazwy w schemacie")
                else:
                    err("UNKNOWN_INPUT", where, f"wejscie {nm} nie istnieje w schemacie")
        # wymagane nie-widgety musza byc podlaczone
        for inp in inputs:
            if inp["required"] and inp["type"] not in WIDGET_TYPES and inp["type"] != "COMBO":
                if inp["name"] not in linked:
                    err("MISSING_LINK", where, f"wymagane wejscie {inp['name']} ({inp['type']}) nie jest podlaczone")
        # widgety: kolejnosc jak w schemacie
        widget_inputs = [i for i in inputs if i["type"] in WIDGET_TYPES or i["type"] == "COMBO"]
        # INT z control_after_generate (np. ziarno) ma dodatkowa wartosc widgetu po wartosci liczbowej
        expanded = []
        for inp in widget_inputs:
            expanded.append((inp, False))
            if inp["type"] == "INT" and inp["meta"].get("control_after_generate"):
                expanded.append((inp, True))
            if inp["type"] == "COMBO" and (inp["meta"].get("image_upload") or inp["meta"].get("video_upload")):
                expanded.append((inp, "upload"))  # widget uploadu w UI (np. LoadImage: "image")
        values = n.get("widgets_values", [])
        if len(values) != len(expanded):
            err("WIDGET_COUNT", where, f"widgets_values ma {len(values)} wartosci, schemat {len(expanded)} widgetow")
        for (inp, is_control), val in zip(expanded, values):
            if is_control == "upload":
                continue  # nazwa widgetu uploadu jest w UI, nie w liscie wyboru
            if is_control:
                if val not in ("fixed", "increment", "decrement", "randomize"):
                    err("COMBO_VALUE_NOT_ALLOWED", f"{where} :: {inp['name']} control", f"{val!r} nie jest trybem kontroli")
                continue
            check_value(err, f"{where} :: {inp['name']}", inp, val)

    # polaczenia
    for lid, fn, fs, tn, ts, ltype in graph.get("links", []):
        src, dst = nodes.get(fn), nodes.get(tn)
        where = f"link {lid}: {fn}[{fs}] -> {tn}[{ts}]"
        if src is None or dst is None:
            err("BAD_LINK_NODE", where, "wezel zrodlowy lub docelowy nie istnieje")
            continue
        s_sch = schema.get(src["type"], {})
        outs = s_sch.get("output", [])
        if fs >= len(outs):
            err("BAD_OUTPUT_SLOT", where, f"{src['type']} ma {len(outs)} wyjsc, a link zrodlowy {fs}")
            continue
        if outs[fs] != ltype:
            err("TYPE_MISMATCH", where, f"wyjscie {fs} {src['type']} to {outs[fs]}, link {ltype}")
        d_sch = schema.get(dst["type"], {})
        d_inputs = {i["name"]: i for i in ordered_inputs(d_sch)}
        try:
            tname = dst["inputs"][ts]["name"]
        except (IndexError, KeyError):
            err("BAD_INPUT_SLOT", where, f"wejscie {ts} wezla docelowego nie istnieje w grafie")
            continue
        if tname in d_inputs and d_inputs[tname]["type"] not in (ltype, "*"):
            err("TYPE_MISMATCH", where, f"wejscie {tname} to {d_inputs[tname]['type']}, link {ltype}")
    return errors, warnings


def validate_api(graph, schema):
    errors, warnings = [], []

    def err(code, where, msg):
        errors.append({"code": code, "where": where, "message": msg})

    for nid, node in graph.items():
        where = f"node {nid} {node.get('class_type')}"
        sch = schema.get(node.get("class_type"))
        if sch is None:
            err("MISSING_NODE", where, f"klasa {node.get('class_type')} nie istnieje w schemacie")
            continue
        inputs = {i["name"]: i for i in ordered_inputs(sch)}
        given = node.get("inputs", {})
        for name, inp in inputs.items():
            if inp["required"] and name not in given and inp["type"] not in ("COMBO",) and inp["meta"].get("default") is None:
                err("MISSING_INPUT", where, f"brak wymaganego wejscia {name}")
        for name, val in given.items():
            if name not in inputs:
                if name.startswith("ref_"):
                    warn_msg = f"wejscie {name} spoza stalego schematu"
                    warnings.append({"code": "AUTOGROW_UNCHECKED", "where": where, "message": warn_msg})
                else:
                    err("UNKNOWN_INPUT", where, f"wejscie {name} nie istnieje w schemacie")
                continue
            if isinstance(val, list) and len(val) == 2 and isinstance(val[0], str):
                src = graph.get(val[0])
                if src is None:
                    err("BAD_LINK_NODE", where, f"{name} wskazuje nieistniejacy wezel {val[0]}")
                    continue
                outs = schema.get(src.get("class_type"), {}).get("output", [])
                slot = val[1]
                if slot >= len(outs):
                    err("BAD_OUTPUT_SLOT", where, f"{name} <- {val[0]}[{slot}], zrodlo ma {len(outs)} wyjsc")
                elif inputs[name]["type"] not in (outs[slot], "*"):
                    err("TYPE_MISMATCH", where, f"{name} ({inputs[name]['type']}) <- {outs[slot]}")
            else:
                check_value(err, f"{where} :: {name}", inputs[name], val)
    return errors, warnings


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("graph")
    ap.add_argument("--schema", required=True, help="plik z zapisanym /object_info")
    ap.add_argument("--out", help="zapis raportu JSON")
    args = ap.parse_args()
    try:
        graph = json.load(open(args.graph, encoding="utf-8"))
        schema = json.load(open(args.schema, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"zly plik wejsciowy: {exc}")
        return 2
    if "nodes" in graph and "links" in graph:
        errors, warnings = validate_ui(graph, schema)
        fmt = "ui"
    else:
        errors, warnings = validate_api(graph, schema)
        fmt = "api"
    report = {"format": fmt, "graph": args.graph, "schema": args.schema, "ok": not errors,
              "errors": errors, "warnings": warnings,
              "note": "walidacja zgodnosci ze schematem; nie dowodzi poprawnego dzialania na GPU"}
    if args.out:
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"{args.graph} [{fmt}]: {'OK' if not errors else 'BLEDY'} "
          f"(bledy: {len(errors)}, ostrzezenia: {len(warnings)})")
    for e in errors:
        print(f"  {e['code']}: {e['where']}: {e['message']}")
    for w in warnings[:10]:
        print(f"  ostrz. {w['code']}: {w['where']}: {w['message']}")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
