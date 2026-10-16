#!/usr/bin/env python3
"""Szlif: przepisywanie Bielikiem i czyszczenie ukrytych znaków, lokalnie.

    python3 szlif.py                 strona w przeglądarce (Windows: py szlif.py)
    python3 szlif.py instaluj        instaluje Ollamę i pobiera Bielika (Windows: py szlif.py instaluj)
    python3 szlif.py przepisz PLIK   przepisuje plik akapit po akapicie, dla skryptów i agentów
"""

import sys

if sys.version_info < (3, 9):
    print("Szlif wymaga Pythona 3.9 lub nowszego.")
    sys.exit(1)

import argparse
import json
import os
import webbrowser
from typing import List, Optional

from szlif_core import COMMAND, config
from szlif_core.backends import BackendError, make_backend
from szlif_core.process import process_text, warning_lines
from szlif_core.rewrite import MODES
from szlif_core.server import make_server
from szlif_core.verify import build_prompt

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
    rw = sub.add_parser("przepisz", help="przepisuje plik akapit po akapicie (dla skryptów i agentów)",
                        description="Kod wyjścia: 0 bez ostrzeżeń, 3 są ostrzeżenia (przeczytaj je), 1 błąd.")
    rw.add_argument("plik", help="plik tekstowy UTF-8 albo - (standardowe wejście)")
    rw.add_argument("--tryb", choices=list(MODES), default="standardowy", help="liczba rund (domyślnie standardowy)")
    rw.add_argument("--wynik", help="zapisz wynik do pliku (domyślnie: standardowe wyjście)")
    rw.add_argument("--raport", help="zapisz raport JSON: akapity przed/po, ostrzeżenia, czyszczenie")
    rw.add_argument("--weryfikacja", help="zapisz prompt do sprawdzenia sensu przez drugi model")
    rw.add_argument("--sprawdz", action="store_true",
                    help="po przepisaniu każ modelowi (lokalnie) porównać każdy akapit z oryginałem")
    rw.add_argument("--model-weryfikatora", help="inny model do sprawdzenia (domyślnie ten sam)")
    rw.add_argument("--bez-czyszczenia", action="store_true", help="nie czyść ukrytych znaków")
    rw.add_argument("--myslniki", action="store_true", help="zamieniaj myślniki na przecinki")
    for name in ("--serwer", "--model", "--rodzaj"):
        rw.add_argument(name, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def rewrite_file(args: argparse.Namespace) -> int:
    """szlif.py przepisz: the page's work without the page, for scripts and agents."""
    def say(text: str, end: str = "\n") -> None:
        print(text, end=end, file=sys.stderr, flush=True)

    try:
        text = sys.stdin.read() if args.plik == "-" else open(args.plik, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError) as e:
        say("Nie mogę przeczytać pliku %s: %s" % (args.plik, e))
        return 1
    if not text.strip():
        say("Plik jest pusty.")
        return 1
    backend = make_backend(args.serwer, args.rodzaj, api_key=os.environ.get("SZLIF_API_KEY"))
    try:
        model = args.model or config.load().get("model")
        if not model:
            models = backend.list_models()
            model = next((m for m in models if "bielik" in m.lower()), models[0] if models else None)
        if not model:
            say("Brak modelu. Uruchom: %s instaluj" % COMMAND)
            return 1
        rounds = MODES[args.tryb]
        result = process_text(backend, model, text, rounds, not args.bez_czyszczenia, args.myslniki,
                              lambda done, todo, rnd: say("\rAkapit %d z %d · runda %d z %d   " % (done, todo, rnd, rounds),
                                                          end=""))
    except BackendError as e:
        say("\n%s" % e)
        return 1
    say("")
    if args.wynik:
        with open(args.wynik, "w", encoding="utf-8") as f:
            f.write(result["wynik"])
    else:
        sys.stdout.write(result["wynik"])
    lines = warning_lines(result)
    prompt = build_prompt([(a["numer"], a["przed"], a["po"]) for a in result["akapity"]], lines)
    if args.weryfikacja:
        with open(args.weryfikacja, "w", encoding="utf-8") as f:
            f.write(prompt)
    check = None
    if args.sprawdz and prompt:
        checker = args.model_weryfikatora or model
        say("Sprawdzam sens modelem %s…" % checker)
        try:
            answer = backend.chat(checker, "Jesteś uważnym weryfikatorem tekstu.", prompt).text.strip()
        except BackendError as e:
            say(str(e))
            return 1
        check = {"model": checker, "odpowiedz": answer}
    if args.raport:
        report = dict(result, model=model, tryb=args.tryb)
        if check:
            report["weryfikacja"] = check
        with open(args.raport, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    say("Szlif: przepisane akapity: %d, ostrzeżenia: %d." % (len(result["akapity"]), result["ostrzezenia"]))
    for line in lines:
        say("  " + line)
    if check:
        say("Weryfikacja (%s):\n%s" % (check["model"], check["odpowiedz"]))
    return 3 if result["ostrzezenia"] else 0


def main(argv: Optional[List[str]] = None) -> int:
    setup_console()
    args = parse_args(argv)
    if args.polecenie == "przepisz":
        return rewrite_file(args)
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
