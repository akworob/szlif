"""Smoke test: start szlif.py with no model server and check that the page loads,
reports the missing server and still cleans text. Exits 0 on success, 1 on failure.

    python tests/smoke.py
"""

import json
import os
import re
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def post(url, body):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    return json.load(OPENER.open(req, timeout=30))


def main():
    proc = subprocess.Popen(
        [sys.executable, "szlif.py", "--bez-przegladarki", "--port", "0", "--serwer", "http://127.0.0.1:9"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    try:
        line = proc.stdout.readline()
        found = re.search(r"http://127\.0\.0\.1:(\d+)", line)
        assert found, "no start line, got: %r" % line
        base = found.group(0)
        page = OPENER.open(base + "/", timeout=30).read().decode("utf-8")
        assert "Szlif" in page, "page has no title"
        stan = json.load(OPENER.open(base + "/api/stan", timeout=30))
        assert stan["blad"], "missing model server not reported: %r" % stan
        view = post(base + "/api/widok", {"tekst": "a​b", "wynik": None, "ukryte": True, "myslniki": False})
        result = "".join(s["text"] for s in view["po"])
        assert result == "ab", "cleaning gave %r" % result
    except Exception as e:  # report any failure as one line, then fail the job
        print("smoke: FAIL: %s" % e)
        return 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    print("smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
