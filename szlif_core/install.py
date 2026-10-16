"""Instalator: installs Ollama, turns its cloud features off and pulls a Bielik
sized to this computer's memory. It asks t/n before every change to the system
and, on "n", prints the command to run by hand.

Everything comes from official sources: Homebrew or winget for Ollama, and the
SpeakLeash repositories on Hugging Face (through Ollama) for the model."""

import ctypes
import json
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Callable, List, Optional, TextIO, Tuple

from . import COMMAND, config
from .backends import BackendError, OllamaBackend
from .cleaner import clean
from .rewrite import run_round

# (minimum RAM in GiB, model, download size)
MODELS = [(24, "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q6_K", "9,2 GB"),
          (12, "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M", "6,7 GB"),
          (0, "hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0", "5,1 GB")]
DOWNLOAD_URL = "https://ollama.com/download"
CLOUD_FILE = Path.home() / ".ollama" / "server.json"
# A short paragraph, not one sentence: asked to vary the rhythm of a single sentence, the model
# tends to pad it with invented content (measured with Bielik 11B v3.0).
TEST_TEXT = ("Uprzejmie informujemy, że spotkanie odbędzie się 9 kwietnia o godz. 18:00 w sali nr 2. "
             "Udział w spotkaniu jest bezpłatny. Prosimy o wcześniejsze potwierdzenie obecności.")

Which = Callable[[str], Optional[str]]


def ram_gb() -> Optional[float]:
    """This computer's memory in GiB, or None when it cannot be read."""
    try:
        system = platform.system()
        if system == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            return int(out.stdout.strip()) / 1024 ** 3
        if system == "Windows":
            class Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = Status()
            status.dwLength = ctypes.sizeof(Status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / 1024 ** 3
            return None
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) / 1024 ** 2
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return None
    return None


def choose_model(ram: Optional[float]) -> Tuple[str, str]:
    if ram is None:
        return MODELS[1][1], MODELS[1][2]
    for minimum, model, size in MODELS:
        if ram >= minimum:
            return model, size
    return MODELS[-1][1], MODELS[-1][2]


def install_command(system: str, which: Which) -> Optional[List[str]]:
    if system == "Darwin" and which("brew"):
        return ["brew", "install", "ollama"]
    if system == "Windows" and which("winget"):
        return ["winget", "install", "-e", "--id", "Ollama.Ollama"]
    return None


def start_command(system: str, which: Which) -> Optional[List[str]]:
    if system == "Darwin" and which("brew"):
        return ["brew", "services", "start", "ollama"]
    if system == "Darwin":
        return ["open", "-a", "Ollama"]
    if system == "Windows":
        return ["cmd", "/c", "start", "", "ollama", "serve"]  # a new window; returns at once
    return None


def set_cloud_off(path: Path) -> Optional[bool]:
    """True: the setting was written; False: it was already there; None: the file
    is not valid JSON and was left alone."""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("disable_ollama_cloud") is True:
        return False
    data["disable_ollama_cloud"] = True
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def ask_yes(question: str) -> bool:
    try:
        return input(question + " [t/n] ").strip().lower() in ("t", "tak")
    except EOFError:
        return False


def _up(base_url: str) -> bool:
    try:
        return isinstance(OllamaBackend(base_url, timeout=3)._request("/api/version", timeout=3), dict)
    except BackendError:
        return False


def _wait_up(base_url: str, seconds: int = 30) -> bool:
    for _ in range(seconds):
        if _up(base_url):
            return True
        time.sleep(1)
    return _up(base_url)


class PullRefused(BackendError):
    """Ollama itself refused the pull (no such model, no disk space): trying again will not help."""


RETRY_ATTEMPTS, RETRY_WAIT = 5, 10  # seconds between attempts; Ollama resumes a partial download


def pull_with_retry(base_url: str, model: str, out: TextIO) -> None:
    """pull(), tried again when the connection breaks off. Measured: a 5 GB pull stopped half way
    and stayed there; asked again, Ollama goes on from where it stopped."""
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            return pull(base_url, model, out)
        except PullRefused:
            raise
        except BackendError as e:
            if attempt == RETRY_ATTEMPTS:
                raise
            print("\nPobieranie przerwane (%s); ponawiam (%d z %d) za %d s, od miejsca przerwania."
                  % (e, attempt + 1, RETRY_ATTEMPTS, RETRY_WAIT), file=out, flush=True)
            time.sleep(RETRY_WAIT)


def pull(base_url: str, model: str, out: TextIO) -> None:
    """Pull a model through Ollama's API, printing one line of progress."""
    backend = OllamaBackend(base_url)
    body = json.dumps({"model": model, "stream": True}).encode()
    req = urllib.request.Request(backend.url + "/api/pull", body, {"Content-Type": "application/json"})
    try:
        finished = False
        with backend._opener.open(req, timeout=300) as resp:
            for raw in resp:
                if not raw.strip():
                    continue
                event = json.loads(raw)
                if event.get("error"):
                    raise PullRefused("Ollama nie pobrała modelu: %s" % event["error"])
                total, done = event.get("total"), event.get("completed")
                if total and done is not None:
                    print("\r%s %d%%   " % (event.get("status", ""), done * 100 // total), end="", file=out, flush=True)
                if event.get("status") == "success":
                    finished = True
                    print("\rPobrano.          ", file=out)
    except (OSError, ValueError) as e:
        raise BackendError("Pobieranie modelu przerwane (%s). Uruchom instalator ponownie." % e)
    if not finished:
        raise BackendError("Pobieranie modelu nie dobiegło końca. Uruchom instalator ponownie.")


def run_installer(base_url: str, ask: Callable[[str], bool], run: Callable[[List[str]], int],
                  which: Which, system: str, out: TextIO, ram: Optional[float],
                  model: Optional[str] = None) -> int:
    """model: a model to install instead of the one chosen by RAM (`instaluj --model`), e.g. to
    check a download on a computer that already has another Bielik."""
    def say(text: str = "") -> None:
        print(text, file=out, flush=True)

    say("Szlif: instalator. Python %s, system %s." % (platform.python_version(), system))
    backend = OllamaBackend(base_url)
    if backend.is_local and not _up(base_url):
        if not which("ollama"):
            cmd = install_command(system, which)
            if cmd is None:
                say("Nie ma Ollamy. Pobierz ją ze strony %s, zainstaluj i uruchom instalator ponownie." % DOWNLOAD_URL)
                return 1
            if not ask("Nie ma Ollamy. Zainstalować ją poleceniem: %s?" % " ".join(cmd)):
                say("Zainstaluj ręcznie: %s, potem uruchom: %s instaluj" % (" ".join(cmd), COMMAND))
                return 1
            if run(cmd) != 0:
                say("Instalacja Ollamy nie powiodła się. Spróbuj ręcznie: %s" % " ".join(cmd))
                return 1
        if not _up(base_url):
            cmd = start_command(system, which)
            if cmd and ask("Ollama nie działa. Uruchomić ją poleceniem: %s?" % " ".join(cmd)):
                run(cmd)
            elif not ask("Uruchom aplikację Ollama. Działa?"):
                return 1
            if not _wait_up(base_url):
                say("Ollama nie odpowiada pod %s. Uruchom ją i spróbuj ponownie." % base_url)
                return 1
    if not backend.is_local and not _up(base_url):
        say("Serwer %s nie odpowiada jak Ollama. Instalator obsługuje tylko Ollamę." % base_url)
        return 1
    say("Ollama działa pod %s." % base_url)

    if backend.is_local:
        cloud = backend.cloud_disabled()
        if cloud is False:
            if ask("Funkcje chmurowe Ollamy są włączone (łączą się z ollama.com). Wyłączyć je (wpis w %s)?"
                   % CLOUD_FILE):
                changed = set_cloud_off(CLOUD_FILE)
                if changed is None:
                    say("Plik %s nie jest poprawnym JSON-em. Dopisz w nim ręcznie: \"disable_ollama_cloud\": true"
                        % CLOUD_FILE)
                elif system == "Darwin" and which("brew"):
                    run(["brew", "services", "restart", "ollama"])
                else:
                    ask("Zamknij Ollamę i uruchom ją ponownie. Gotowe?")
                _wait_up(base_url)
                say("Funkcje chmurowe: %s." % ("wyłączone" if backend.cloud_disabled() else "nadal włączone"))
            else:
                say("Funkcje chmurowe zostają włączone. Strona Szlifu będzie o tym przypominać.")
        elif cloud:
            say("Funkcje chmurowe Ollamy są wyłączone.")

    forced = model is not None
    if forced:
        size = next((s for _, m, s in MODELS if m == model), "rozmiar nieznany")
        say("Model wskazany ręcznie: %s (%s)." % (model, size))
    else:
        model, size = choose_model(ram)
        say("Pamięć RAM: %s. Model dla tego komputera: %s (%s)."
            % ("%.0f GB" % ram if ram else "nieznana", model, size))
    try:
        installed = backend.list_models()
    except BackendError as e:
        say(str(e))
        return 1
    if model not in installed:
        other = None if forced else next((m for m in installed if "bielik" in m.lower()), None)
        if other:
            model = other
            say("Używam Bielika, który już jest: %s." % model)
        elif ask("Pobrać model %s (%s)?" % (model, size)):
            try:
                pull_with_retry(base_url, model, out)
            except BackendError as e:
                say(str(e))
                return 1
        else:
            say("Pobierz ręcznie: ollama pull %s" % model)
            return 1
    else:
        say("Model jest już pobrany.")

    say("Próba na krótkim akapicie…")
    try:
        result = run_round(backend, model, clean(TEST_TEXT).text, TEST_TEXT, 2, True, False)
    except BackendError as e:
        say("Próba nie powiodła się: %s" % e)
        return 1
    if not result["tekst"]:  # from round 2 on, run_round reports an error instead of raising it
        say("Próba nie powiodła się: %s" % result["powod"])
        return 1
    say("  przed: " + TEST_TEXT)
    say("  po:    " + result["tekst"])
    for problem in result["problemy"]:
        say("  uwaga: " + problem["message"])
    config.save(dict(config.load(), model=model))
    say("Gotowe. Uruchom: %s" % COMMAND)
    return 0


def main(base_url: str, model: Optional[str] = None) -> int:
    return run_installer(base_url, ask_yes, lambda cmd: subprocess.call(cmd), shutil.which,
                         platform.system(), sys.stdout, ram_gb(), model)
