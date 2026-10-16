"""Updates: is there a newer Szlif on GitHub, and getting it.

Szlif talks to nothing but the model server unless the user says so: the check at start runs
only when the user agreed to it in the installer (config "aktualizacje"), at most once a day, and
`szlif.py aktualizuj` runs only when typed. A git clone is updated with `git pull --ff-only`
(never over local changes); a copy from a ZIP gets the release's files written over it."""

import http.client
import io
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, TextIO, Tuple

from . import __version__

REPO = "akworob/szlif"
LATEST = "https://api.github.com/repos/%s/releases/latest" % REPO
GITHUB_HOSTS = {"api.github.com", "github.com", "codeload.github.com"}
DAY = 24 * 3600
CONSENT_QUESTION = "Sprawdzać przy starcie, czy jest nowa wersja Szlifu? Jedno zapytanie do GitHuba raz na dobę, bez wysyłania tekstów."
ROOT = Path(__file__).resolve().parent.parent

Run = Callable[[list], Tuple[int, str]]


class UpdateError(Exception):
    """str(e) is a message for the user, in Polish."""


def _version(text: str) -> Optional[Tuple[int, ...]]:
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip())
    return tuple(int(part) for part in m.group(1).split(".")) if m else None


def newer(latest: str, current: str) -> bool:
    a, b = _version(latest), _version(current)
    return bool(a and b and a > b)


def check_due(config: Dict, now: float) -> bool:
    """True when the user agreed to checks and the last one is a day old or more."""
    return config.get("aktualizacje") is True and now - float(config.get("sprawdzono", 0)) >= DAY


def latest_release(url: str = LATEST, timeout: float = 5) -> Optional[Dict]:
    """The newest release ({"wersja", "adres", "zip", "opis"}), or None when it cannot be told."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "szlif"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
        return {"wersja": str(data["tag_name"]).lstrip("v"), "adres": data["html_url"],
                "zip": data["zipball_url"], "opis": str(data.get("body") or "")[:500]}
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError, http.client.HTTPException):
        return None


def install_kind(root: Path) -> str:
    return "git" if (root / ".git").is_dir() else "zip"


def _run(cmd: list) -> Tuple[int, str]:
    done = subprocess.run(cmd, capture_output=True, text=True)
    return done.returncode, done.stdout + done.stderr


def update_git(root: Path, run: Run, out: TextIO) -> int:
    # Untracked files (wynik.txt from the README examples) are no reason to refuse: pull keeps them.
    code, status = run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"])
    if code != 0:
        print("Nie mogę sprawdzić stanu repozytorium: %s" % status.strip(), file=out)
        return 1
    if status.strip():
        print("Masz lokalne zmiany w plikach Szlifu, a aktualizacja by je nadpisała. Zapisz je "
              "(np. git stash) i spróbuj ponownie.", file=out)
        return 1
    before = run(["git", "-C", str(root), "rev-parse", "HEAD"])[1].strip()
    code, log = run(["git", "-C", str(root), "pull", "--ff-only"])
    if code != 0:
        print("git pull się nie udał: %s" % log.strip(), file=out)
        return code
    if run(["git", "-C", str(root), "rev-parse", "HEAD"])[1].strip() == before:
        # e.g. a fork as origin: "up to date", yet the release is not there
        print("git pull nie przyniósł nowej wersji: ta kopia pobiera zmiany z innego miejsca niż "
              "https://github.com/%s. Pobierz nową wersję stamtąd." % REPO, file=out)
        return 1
    return 0


def update_zip(root: Path, url: str, out: TextIO, allowed_hosts: Iterable[str] = GITHUB_HOSTS) -> None:
    """Download a release ZIP from GitHub and write its files over root. Files that are not in the
    release stay; a path that would leave root is skipped. Half an update is worse than none, so
    every file is read (which checks it) and written next to its target first; only then are the
    old files replaced."""
    allowed = set(allowed_hosts)
    if urllib.parse.urlsplit(url).hostname not in allowed:
        raise UpdateError("Adres paczki %s nie jest adresem GitHuba." % url)
    base, files = root.resolve(), []
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "szlif"}), timeout=60) as resp:
            if urllib.parse.urlsplit(resp.geturl()).hostname not in allowed:
                raise UpdateError("Paczka przekierowała poza GitHuba (%s)." % resp.geturl())
            data = resp.read()
        archive = zipfile.ZipFile(io.BytesIO(data))
        for member in archive.infolist():
            parts = member.filename.split("/")[1:]  # GitHub puts everything in one top folder
            if member.is_dir() or not parts or not parts[-1] or ".." in parts or member.filename.startswith("/"):
                continue
            target = (base / Path(*parts)).resolve()
            if base in target.parents:
                files.append((target, archive.read(member)))  # a damaged file fails here (CRC)
    except (OSError, zipfile.BadZipFile, urllib.error.URLError, http.client.HTTPException) as e:
        raise UpdateError("Nie udało się pobrać nowej wersji: %s" % e)
    staged: List[Tuple[Path, Path]] = []
    try:
        for target, content in files:
            if target.exists():
                with open(target, "ab"):  # a read-only or locked file fails here, before anything changes
                    pass
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_name(target.name + ".szlif-nowy")
            temp.write_bytes(content)
            staged.append((temp, target))
    except OSError as e:
        _remove(temp for temp, _ in staged)
        raise UpdateError("Nie mogę zapisać nowej wersji (%s). Niczego nie zmieniono. Zamknij programy, "
                          "które mogą używać plików Szlifu, i spróbuj ponownie." % e)
    for done, (temp, target) in enumerate(staged):
        try:
            os.replace(temp, target)
        except OSError as e:
            _remove(temp for temp, _ in staged[done:])
            raise UpdateError("Zapis nowej wersji przerwany (%s): część plików jest nowa, część stara. "
                              "Uruchom aktualizację jeszcze raz albo pobierz ZIP od nowa." % e)
    print("Zapisano %d plików nowej wersji." % len(staged), file=out)


def _remove(paths: Iterable[Path]) -> None:
    for path in paths:
        try:
            path.unlink()
        except OSError:
            pass


def run_update(out: TextIO, root: Path = ROOT, release: Optional[Dict] = None,
               which: Callable[[str], Optional[str]] = shutil.which, run: Run = _run) -> int:
    """`szlif.py aktualizuj`: 0 updated or already the newest, 1 not possible."""
    release = release or latest_release()
    if release is None:
        print("Nie mogę sprawdzić najnowszej wersji: brak połączenia z GitHubem albo brak wydań.", file=out)
        return 1
    if not newer(release["wersja"], __version__):
        print("Masz najnowszą wersję Szlifu (%s)." % __version__, file=out)
        return 0
    print("Nowa wersja %s (masz %s): %s" % (release["wersja"], __version__, release["adres"]), file=out)
    if install_kind(root) == "git" and not which("git"):
        # Never write a ZIP over a clone: e.g. GitHub Desktop has no git command on PATH.
        print("To kopia z gita, ale nie widzę polecenia git. Pobierz zmiany w programie, którym "
              "kopia została sklonowana (np. GitHub Desktop: Fetch origin, potem Pull), albo zainstaluj git.", file=out)
        return 1
    try:
        code = update_git(root, run, out) if install_kind(root) == "git" else (
            update_zip(root, release["zip"], out) or 0)
    except UpdateError as e:
        print(str(e), file=out)
        return 1
    if code == 0:
        print("Gotowe. Uruchom Szlif ponownie, żeby działała nowa wersja.", file=out)
    return code


def stamp(config: Dict, now: Optional[float] = None) -> Dict:
    return dict(config, sprawdzono=time.time() if now is None else now)
