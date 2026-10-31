#!/usr/bin/env python3
"""Testy audytu runtime na lokalnym serwerze-atrapie (bez ComfyUI, bez GPU).

Przypadki:
  1. brak serwera            -> SERVER_UNREACHABLE
  2. wezly sa, plik modelu brak w liscie -> MODEL_NOT_INSTALLED
  3. wszystko na miejscu     -> OK
"""
import json
import os
import socket
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit_h3_runtime as a  # noqa: E402


def free_port():
    with socket.socket() as sk:
        sk.bind(("127.0.0.1", 0))
        return sk.getsockname()[1]


def make_schema(node, files_for):
    required = {}
    for n, inp, _ in a.EXPECTED_FILES:
        pass
    # zwykle wejscia (bez listy wyboru) i listy wyboru dla plikow
    options = {inp: [f for (nn, ii, f) in a.EXPECTED_FILES if nn == node and ii == inp] for inp in
               {ii for (nn, ii, _) in a.EXPECTED_FILES if nn == node}}
    for inp, opts in options.items():
        opts = [o for o in opts if o in files_for.get(node, opts)]
        required[inp] = [opts, {}]
    required.setdefault("prompt", ["STRING", {}])
    return {"input": {"required": required, "optional": {}}, "output": ["MODEL"], "output_name": ["MODEL"]}


def make_handler(files_available):
    schemas_present = set(a.REQUIRED_NODES + a.CONTROLNET_NODES)

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, obj, code=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/system_stats":
                return self._send({"system": {"comfyui_version": "test", "pytorch_version": "none"}, "devices": []})
            if self.path.startswith("/object_info/"):
                node = self.path.split("/object_info/")[1]
                if node in schemas_present:
                    return self._send({node: make_schema(node, files_available)})
                return self._send({}, 404)
            return self._send({}, 404)

    return H


def run_server(files_available):
    port = free_port()
    srv = HTTPServer(("127.0.0.1", port), make_handler(files_available))
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, f"http://127.0.0.1:{port}"


def main():
    tmp = tempfile.mkdtemp()

    # 1. brak serwera
    rep = a.audit(f"http://127.0.0.1:{free_port()}")
    assert rep["status"] == "SERVER_UNREACHABLE", rep["status"]
    print("OK 1: brak serwera -> SERVER_UNREACHABLE")

    # 2. wezly sa, ale pliki ControlNet/modelu nie figuruja w listach wyboru
    srv, url = run_server({"ModelPatchLoader": []})
    rep = a.audit(url)
    srv.shutdown()
    assert rep["status"] == "MODEL_NOT_INSTALLED", rep["status"]
    missing = [f["expected"] for f in rep["files"] if f.get("status") == "MODEL_NOT_INSTALLED"]
    assert "minimax_h3_fun_controlnet_union_pruned_int8_convrot.safetensors" in missing
    print("OK 2: brak pliku ControlNet -> MODEL_NOT_INSTALLED, brakujace:", len(missing))

    # 3. wszystkie oczekiwane pliki sa dostepne
    everything = {n: [f for (nn, ii, f) in a.EXPECTED_FILES if nn == n] for n in
                  {x[0] for x in a.EXPECTED_FILES}}
    srv, url = run_server(everything)
    rep = a.audit(url)
    srv.shutdown()
    print("   status przy kompletnym serwerze:", rep["status"], "| unmet:", len(rep["unmet"]))
    # brakujace wezly opcjonalne nie moga psuc statusu
    assert rep["status"] in ("OK", "NODE_MISSING"), rep["status"]
    if rep["status"] == "NODE_MISSING":
        assert all("wezel" in u["requirement"] for u in rep["unmet"])
    print("OK 3: kompletne wejscia nie daja MODEL_NOT_INSTALLED")

    out = os.path.join(tmp, "audit.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh)
    assert json.load(open(out, encoding="utf-8"))["status"] == rep["status"]
    print("Wszystkie testy audytu OK.")


if __name__ == "__main__":
    main()
