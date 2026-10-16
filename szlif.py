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
import time
import webbrowser
from typing import Dict, List, Optional

from szlif_core import COMMAND, __version__, config, install, update
from szlif_core.backends import BackendError, make_backend
from szlif_core.process import process_text, warning_lines
from szlif_core.rewrite import MODES, PURPOSE, READABILITY
from szlif_core.server import make_server
from szlif_core.verify import build_prompt, check_meaning

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
    p.add_argument("--wersja", action="version", version="Szlif %s" % __version__, help="pokaż wersję i zakończ")
    sub = p.add_subparsers(dest="polecenie")
    installer = sub.add_parser("instaluj", help="instaluje Ollamę i pobiera Bielika")
    installer.add_argument("--serwer", default=argparse.SUPPRESS, help="adres Ollamy (domyślnie lokalna)")
    installer.add_argument("--model", default=argparse.SUPPRESS,
                           help="zainstaluj ten model zamiast dobranego do pamięci RAM")
    sub.add_parser("aktualizuj", help="pobiera najnowszą wersję Szlifu z GitHuba")
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
    rw.add_argument("--czytelnosc", choices=list(READABILITY), default="normalna", help="czytelność tekstu")
    rw.add_argument("--cel", choices=list(PURPOSE), default="ogolny", help="cel tekstu (styl)")
    for name in ("--serwer", "--model", "--rodzaj"):
        rw.add_argument(name, default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return p.parse_args(argv)


def _writable(path: str) -> bool:
    folder = os.path.dirname(os.path.abspath(path))
    return os.path.isdir(folder) and os.access(folder, os.W_OK)


def _read_input(name: str) -> str:
    """UTF-8 from a file or from standard input; on Windows a pipe would otherwise be read in
    the console's code page and Polish letters would silently turn into other ones."""
    if name == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with open(name, encoding="utf-8-sig") as f:
        return f.read()


def rewrite_file(args: argparse.Namespace) -> int:
    """szlif.py przepisz: the page's work without the page, for scripts and agents."""
    def say(text: str, end: str = "\n") -> None:
        print(text, end=end, file=sys.stderr, flush=True)

    outputs = [p for p in (args.wynik, args.raport, args.weryfikacja) if p]
    unwritable = [p for p in outputs if not _writable(p)]
    if unwritable:  # before any model work, which can take minutes
        say("Nie mogę zapisać pliku: %s (brak folderu albo uprawnień)." % ", ".join(unwritable))
        return 1
    try:
        text = _read_input(args.plik)
    except (OSError, UnicodeDecodeError) as e:
        say("Nie mogę przeczytać pliku %s: %s" % (args.plik, e))
        return 1
    if not text.strip():
        say("Plik jest pusty.")
        return 1
    backend = make_backend(args.serwer, args.rodzaj, api_key=os.environ.get("SZLIF_API_KEY"))
    rounds = MODES[args.tryb]
    tty = sys.stderr.isatty()

    def progress(done: int, todo: int, rnd: int) -> None:
        if tty:
            say("\rAkapit %d z %d do przepisania · runda %d z %d   " % (done, todo, rnd, rounds), end="")

    try:
        model = args.model or config.load().get("model")
        if not model:
            models = backend.list_models()
            model = next((m for m in models if "bielik" in m.lower()), models[0] if models else None)
        if not model:
            say("Brak modelu. Uruchom: %s instaluj" % COMMAND)
            return 1
        say("Model: %s" % model)
        result = process_text(backend, model, text, rounds, not args.bez_czyszczenia, args.myslniki, progress,
                              args.czytelnosc, args.cel)
    except BackendError as e:
        say("\n%s" % e)
        return 1
    except KeyboardInterrupt:
        say("\nPrzerwano.")
        return 1
    if tty:
        say("")
    lines = warning_lines(result)
    terms = ("Słowa z oryginału, których nie ma w wyniku: %s" % ", ".join(result["znikniete"])
             if result["znikniete"] else "")
    pairs = [(a["numer"], a["przed"], a["po"]) for a in result["akapity"]]
    check = None
    if args.sprawdz and any(before.strip() != after.strip() for _, before, after in pairs):
        checker = args.model_weryfikatora or model
        say("Sprawdzam sens modelem %s…" % checker)
        check = check_meaning(backend, checker, pairs, lines + ([terms] if terms else []))
    report = dict(result, model=model, tryb=args.tryb)
    if check:
        report["weryfikacja"] = check
    try:
        if args.wynik:
            with open(args.wynik, "w", encoding="utf-8") as f:
                f.write(result["wynik"])
        else:
            sys.stdout.write(result["wynik"])
        if args.raport:
            with open(args.raport, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        if args.weryfikacja:
            with open(args.weryfikacja, "w", encoding="utf-8") as f:
                f.write(build_prompt(pairs, lines + ([terms] if terms else [])))
    except OSError as e:
        say("Nie mogę zapisać wyniku: %s" % e)
        return 1
    say("Szlif: przepisane akapity: %d, ostrzeżenia: %d." % (len(result["akapity"]), result["ostrzezenia"]))
    for line in lines:
        say("  " + line)
    if terms:
        say("  " + terms + " (mogło je zastąpić inne słowo, ale mogły też zniknąć z treści)")
    if check:
        say("Weryfikacja (%s):\n%s" % (check["model"], check["odpowiedz"]))
        if "blad" in check:
            say("Weryfikacja nie powiodła się: %s" % check["blad"])
    return 3 if result["ostrzezenia"] else 0


def startup_update_check(ask, out) -> Optional[Dict]:
    """At start, only when the user agreed and at most once a day: a newer release, offered for
    update now (t/n). Who never answered (installed before updates existed) is asked once, but only
    in a terminal; ask is None without one. Returns {"wersja", "adres"} for the page, or
    {"zaktualizowano": True} when Szlif was just updated and must be started again."""
    try:
        settings = config.load()
        if "aktualizacje" not in settings and ask is not None:
            settings["aktualizacje"] = ask(update.CONSENT_QUESTION)
            config.save(settings)
        if not update.check_due(settings, time.time()):
            return None
        release = update.latest_release()
        config.save(update.stamp(settings))
    except OSError as e:  # e.g. a read-only home folder: the check is not worth a Szlif that does not start
        print("Nie udało się sprawdzić nowej wersji: %s" % e, file=out, flush=True)
        return None
    if not release or not update.newer(release["wersja"], __version__):
        return None
    print("Jest nowa wersja Szlifu: %s (masz %s). %s" % (release["wersja"], __version__, release["adres"]),
          file=out, flush=True)
    if ask is not None and ask("Zaktualizować teraz?") and update.run_update(out, release=release) == 0:
        return {"zaktualizowano": True}
    return {"wersja": release["wersja"], "adres": release["adres"]}


def main(argv: Optional[List[str]] = None) -> int:
    setup_console()
    args = parse_args(argv)
    if args.polecenie == "przepisz":
        return rewrite_file(args)
    if args.polecenie == "aktualizuj":
        return update.run_update(sys.stdout)
    if args.polecenie == "instaluj":
        try:
            return install.main(args.serwer, args.model)
        except KeyboardInterrupt:
            print("\nPrzerwano.")
            return 1
    terminal = sys.stdin is not None and sys.stdin.isatty()  # sys.stdin is None under pythonw
    try:
        found = startup_update_check(install.ask_yes if terminal else None, sys.stdout)
    except KeyboardInterrupt:
        print("\nPrzerwano.")
        return 1
    if found and found.get("zaktualizowano"):
        return 0
    backend = make_backend(args.serwer, args.rodzaj, api_key=os.environ.get("SZLIF_API_KEY"))
    server = make_server(backend, args.model or config.load().get("model"), args.port, found)
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
