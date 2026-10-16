#!/usr/bin/env python3
"""Szlif: przepisywanie Bielikiem i czyszczenie ukrytych znaków, lokalnie.

    python3 szlif.py                 strona w przeglądarce (Windows: py szlif.py)
    python3 szlif.py instaluj        instaluje Ollamę i pobiera Bielika (Windows: py szlif.py instaluj)
"""

import sys

if sys.version_info < (3, 9):
    print("Szlif wymaga Pythona 3.9 lub nowszego.")
    sys.exit(1)

import argparse
import os
import webbrowser
from typing import List, Optional

from szlif_core import config
from szlif_core.backends import make_backend
from szlif_core.server import make_server

DEFAULT_SERVER = "http://127.0.0.1:11434"


def setup_console() -> None:
    """Polish letters must print on a Windows console too (cp1252, cp852)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="szlif.py", description=__doc__.split("\n")[0])
    p.add_argument("--serwer", default=os.environ.get("SZLIF_SERWER") or DEFAULT_SERVER,
                   help="adres serwera z modelem (domyślnie lokalna Ollama, %s)" % DEFAULT_SERVER)
    p.add_argument("--rodzaj", choices=["ollama", "openai"],
                   help="rodzaj serwera; domyślnie rozpoznawany sam")
    p.add_argument("--model", help="nazwa modelu (domyślnie ten, który wybrał instalator)")
    p.add_argument("--port", type=int, default=8765, help="port strony (domyślnie 8765)")
    p.add_argument("--bez-przegladarki", action="store_true", help="nie otwieraj przeglądarki")
    sub = p.add_subparsers(dest="polecenie")
    installer = sub.add_parser("instaluj", help="instaluje Ollamę i pobiera Bielika")
    installer.add_argument("--serwer", default=argparse.SUPPRESS, help="adres Ollamy (domyślnie lokalna)")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    setup_console()
    args = parse_args(argv)
    if args.polecenie == "instaluj":
        from szlif_core import install
        try:
            return install.main(args.serwer)
        except KeyboardInterrupt:
            print("\nPrzerwano.")
            return 1
    backend = make_backend(args.serwer, args.rodzaj, api_key=os.environ.get("SZLIF_API_KEY"))
    server = make_server(backend, args.model or config.load().get("model"), args.port)
    url = "http://127.0.0.1:%d" % server.server_address[1]
    print("Szlif działa: %s  (Ctrl+C kończy)" % url, flush=True)
    if not backend.is_local:
        print("Uwaga: tekst będzie wysyłany do %s, poza ten komputer." % backend.url, flush=True)
    if not args.bez_przegladarki:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Zatrzymano.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
