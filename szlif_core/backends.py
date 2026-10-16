"""The model server: Ollama (local or on another computer) or any server that
speaks the OpenAI chat API (vLLM, LM Studio, llama.cpp, a hosted provider).

Redirects are never followed, since one could send the text to another host,
and a server on this computer is reached without any proxy."""

import http.client
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, List, Optional

from . import COMMAND

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


class BackendError(Exception):
    """str(e) is a message for the user, in Polish."""


class Unreachable(BackendError):
    """No answer at all: nothing listens there, or it did not answer in time."""


@dataclass
class Reply:
    text: str
    cut: bool


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Backend:
    kind = ""
    LIST_TIMEOUT = 10.0  # the page waits on the model list, so it must not wait for the long chat timeout

    def __init__(self, url: str, timeout: float = 900.0, api_key: Optional[str] = None):
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key
        self.is_local = (urllib.parse.urlsplit(self.url).hostname or "") in LOCAL_HOSTS
        handlers = [_NoRedirect()]
        if self.is_local:
            handlers.append(urllib.request.ProxyHandler({}))
        self._opener = urllib.request.build_opener(*handlers)

    def list_models(self) -> List[str]:
        raise NotImplementedError

    def chat(self, model: str, system: str, user: str) -> Reply:
        raise NotImplementedError

    def cloud_disabled(self) -> Optional[bool]:
        return None

    def _base(self) -> str:
        return self.url

    def _headers(self) -> dict:
        return {"Content-Type": "application/json"}

    def _request(self, path: str, body: Optional[dict] = None, timeout: Optional[float] = None,
                 on_404: Optional[str] = None, missing_ok: bool = False) -> Any:
        """The JSON answer of one call; None for a 404 when missing_ok."""
        timeout = self.timeout if timeout is None else timeout
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self._base() + path, data, self._headers())
        try:
            with self._opener.open(req, timeout=timeout) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 404 and missing_ok:
                return None
            if e.code == 404 and on_404:
                raise BackendError(on_404)
            if e.code in (401, 403):
                raise BackendError("Serwer odrzucił klucz API. Ustaw zmienną SZLIF_API_KEY.")
            try:
                detail = " ".join(e.read().decode(errors="replace").split())[:200]
            except (OSError, http.client.HTTPException):
                detail = ""
            raise BackendError("Serwer modelu odpowiedział błędem %d: %s" % (e.code, detail))
        except (socket.timeout, TimeoutError):
            raise Unreachable("Serwer modelu nie odpowiedział w %g s. Spróbuj krótszego tekstu." % timeout)
        except urllib.error.URLError as e:
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise Unreachable("Serwer modelu nie odpowiedział w %g s. Spróbuj krótszego tekstu." % timeout)
            raise Unreachable("Nie mogę połączyć się z serwerem modelu (%s). Czy Ollama działa? "
                              "Uruchom: %s instaluj" % (self.url, COMMAND))
        except (OSError, http.client.HTTPException):
            raise Unreachable("Nie mogę połączyć się z serwerem modelu (%s). Czy Ollama działa? "
                              "Uruchom: %s instaluj" % (self.url, COMMAND))
        except ValueError:
            raise BackendError("Serwer modelu zwrócił odpowiedź w nieznanym formacie.")


def _unknown_format() -> BackendError:
    return BackendError("Serwer modelu zwrócił odpowiedź w nieznanym formacie.")


class OllamaBackend(Backend):
    kind = "ollama"

    def list_models(self) -> List[str]:
        reply = self._request("/api/tags", timeout=self.LIST_TIMEOUT)
        try:
            return [m["name"] for m in reply["models"]]
        except (TypeError, KeyError):
            raise _unknown_format()

    def chat(self, model: str, system: str, user: str) -> Reply:
        reply = self._request("/api/chat", {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": 0.3, "num_ctx": 16384},
            # Without these two, Ollama silently drops part of a long prompt.
            "truncate": False,
            "shift": False,
        }, on_404="Brak modelu %s. Uruchom: ollama pull %s" % (model, model))
        message = reply.get("message") if isinstance(reply, dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str):
            raise _unknown_format()
        return Reply(text, reply.get("done_reason") not in (None, "stop"))

    def cloud_disabled(self) -> Optional[bool]:
        try:
            reply = self._request("/api/status", timeout=5, missing_ok=True)
        except BackendError:
            return None
        if not isinstance(reply, dict):
            return None
        cloud = reply.get("cloud")
        return isinstance(cloud, dict) and cloud.get("disabled") is True


class OpenAIBackend(Backend):
    kind = "openai"

    def _base(self) -> str:
        return self.url if urllib.parse.urlsplit(self.url).path.endswith("/v1") else self.url + "/v1"

    def _headers(self) -> dict:
        headers = super()._headers()
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        return headers

    def list_models(self) -> List[str]:
        reply = self._request("/models", timeout=self.LIST_TIMEOUT)
        try:
            return [m["id"] for m in reply["data"]]
        except (TypeError, KeyError):
            raise _unknown_format()

    def chat(self, model: str, system: str, user: str) -> Reply:
        reply = self._request("/chat/completions", {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": 0.3,
        }, on_404="Serwer nie zna modelu %s albo adresu API. Sprawdź --model i --serwer." % model)
        try:
            choice = reply["choices"][0]
            text = choice["message"]["content"]
        except (TypeError, KeyError, IndexError):
            raise _unknown_format()
        if not isinstance(text, str):
            raise _unknown_format()
        return Reply(text, choice.get("finish_reason") == "length")


def make_backend(url: str, kind: Optional[str] = None, timeout: float = 900.0,
                 api_key: Optional[str] = None) -> Backend:
    """kind None: Ollama if it answers /api/version or nothing answers at all, else OpenAI."""
    if kind is None:
        try:
            reply = OllamaBackend(url, timeout=5)._request("/api/version", timeout=5)
            kind = "ollama" if isinstance(reply, dict) and "version" in reply else "openai"
        except Unreachable:
            kind = "ollama"
        except BackendError:
            kind = "openai"
    cls = OllamaBackend if kind == "ollama" else OpenAIBackend
    return cls(url, timeout=timeout, api_key=api_key)
