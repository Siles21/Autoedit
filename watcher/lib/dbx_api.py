#!/usr/bin/env python3
"""dbx_api.py — minimaler Dropbox-API-v2-Client, nur mit der Python-Stdlib.

Absichtlich ohne `dropbox`-SDK: der Watcher soll auf jedem Mac ohne pip-Install
laufen. Abgedeckt ist genau, was Part 1 braucht:

  * OAuth2 **PKCE**-Flow (kein App-Secret auf der Platte) + Refresh-Token
  * `files/list_folder` (+ `/continue`) für Bestand und Deltas
  * `files/list_folder/longpoll` — blockiert bis Dropbox eine Änderung meldet
    (kein Polling, keine API-Limits, Reaktion in Sekunden)
  * `files/get_temporary_link` — direkter Download-Link für Part 2
  * Dropbox **Business/Team**: Select-User + Path-Root-Header

Alle Methoden werfen `DropboxError` mit lesbarer Meldung. 429/5xx werden mit
Backoff wiederholt, 401 löst einen Token-Refresh aus.

    python3 dbx_api.py --selftest     # offline: nur Header-/Parse-Logik
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.dropboxapi.com/2"
NOTIFY = "https://notify.dropboxapi.com/2"
OAUTH_TOKEN_URL = "https://api.dropbox.com/oauth2/token"
OAUTH_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"

USER_AGENT = "autoedit-dropbox-watcher/1.0"
MAX_RETRIES = 5


class DropboxError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


# --- PKCE-Auth (einmalig, interaktiv) --------------------------------------

def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) nach RFC 7636 / S256."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def authorize_url(app_key: str, code_challenge: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": app_key,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "token_access_type": "offline",   # -> Refresh-Token, läuft nie ab
    })
    return f"{OAUTH_AUTHORIZE_URL}?{q}"


def exchange_code(app_key: str, code: str, code_verifier: str) -> dict:
    """Auth-Code -> {"access_token","refresh_token","account_id",...}."""
    return _form_post(OAUTH_TOKEN_URL, {
        "code": code.strip(),
        "grant_type": "authorization_code",
        "client_id": app_key,
        "code_verifier": code_verifier,
    })


def _form_post(url: str, fields: dict) -> dict:
    data = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": USER_AGENT,
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:  # pragma: no cover - Netzpfad
        body = exc.read().decode("utf-8", "replace")
        raise DropboxError(f"OAuth fehlgeschlagen ({exc.code}): {body}", exc.code, body) from exc
    except urllib.error.URLError as exc:  # pragma: no cover
        raise DropboxError(f"Keine Verbindung zu Dropbox: {exc.reason}") from exc


# --- Client ----------------------------------------------------------------

class DropboxClient:
    """Dünner RPC-Client. `refresh_token` + `app_key` genügen (PKCE-App)."""

    def __init__(self, app_key: str, refresh_token: str, app_secret: str = "",
                 team_member_id: str = "", path_root: str = "", access_token: str = ""):
        if not refresh_token and not access_token:
            raise DropboxError("Kein refresh_token/access_token — erst `dbx_watch.py auth` laufen lassen.")
        self.app_key = app_key
        self.app_secret = app_secret
        self.refresh_token = refresh_token
        self.team_member_id = team_member_id
        self.path_root = path_root
        self._access_token = access_token
        self._expires_at = 0.0 if not access_token else time.time() + 300

    # -- Auth
    def _ensure_token(self) -> str:
        if self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        if not self.refresh_token:
            return self._access_token
        fields = {"grant_type": "refresh_token", "refresh_token": self.refresh_token,
                  "client_id": self.app_key}
        if self.app_secret:
            fields["client_secret"] = self.app_secret
        data = _form_post(OAUTH_TOKEN_URL, fields)
        self._access_token = data["access_token"]
        self._expires_at = time.time() + float(data.get("expires_in", 14400))
        return self._access_token

    def headers(self, authed: bool = True) -> dict:
        """Request-Header inkl. Team-/Namespace-Routing (ohne Netzzugriff testbar)."""
        h = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        if authed:
            h["Authorization"] = f"Bearer {self._access_token}"
        if self.team_member_id:
            h["Dropbox-API-Select-User"] = self.team_member_id
        if self.path_root:
            root = self.path_root
            if root in ("home", "root"):
                h["Dropbox-API-Path-Root"] = json.dumps({".tag": "home"})
            else:
                h["Dropbox-API-Path-Root"] = json.dumps({".tag": "namespace_id",
                                                         "namespace_id": str(root)})
        return h

    # -- RPC
    def rpc(self, endpoint: str, payload: dict | None, *, base: str = API, authed: bool = True,
            timeout: int = 60) -> dict:
        url = f"{base}/{endpoint.lstrip('/')}"
        if authed:
            self._ensure_token()
        last: DropboxError | None = None
        for attempt in range(MAX_RETRIES):
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                         headers=self.headers(authed), method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return json.loads(resp.read().decode("utf-8") or "{}")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                if exc.code == 401 and authed and self.refresh_token:
                    self._expires_at = 0.0           # Token abgelaufen -> erneuern
                    self._ensure_token()
                    last = DropboxError("401 unauthorized", 401, body)
                    continue
                if exc.code == 429 or 500 <= exc.code < 600:
                    wait = _retry_after(exc, body, attempt)
                    last = DropboxError(f"{exc.code} von Dropbox: {body[:200]}", exc.code, body)
                    time.sleep(wait)
                    continue
                raise DropboxError(_explain(endpoint, exc.code, body), exc.code, body) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last = DropboxError(f"Netzfehler bei {endpoint}: {exc}")
                time.sleep(min(2 ** attempt, 30))
        raise last or DropboxError(f"{endpoint} nach {MAX_RETRIES} Versuchen fehlgeschlagen")

    # -- Komfort-Methoden
    def account(self) -> dict:
        # Dieser Endpoint erwartet einen leeren Body (JSON `null`).
        return self.rpc("users/get_current_account", None)

    def list_folder(self, path: str, recursive: bool = True, limit: int = 2000) -> tuple[list[dict], str]:
        """Bestand eines Ordners holen. -> (file_entries, cursor)."""
        payload = {
            "path": _api_path(path),
            "recursive": recursive,
            "include_deleted": False,
            "include_media_info": False,
            "include_mounted_folders": True,
            "include_non_downloadable_files": False,
            "limit": limit,
        }
        data = self.rpc("files/list_folder", payload)
        entries = list(data.get("entries", []))
        while data.get("has_more"):
            data = self.rpc("files/list_folder/continue", {"cursor": data["cursor"]})
            entries += list(data.get("entries", []))
        return [e for e in entries if e.get(".tag") == "file"], data.get("cursor", "")

    def list_folder_continue(self, cursor: str) -> tuple[list[dict], str]:
        """Delta seit `cursor`. -> (file_entries, neuer cursor)."""
        entries: list[dict] = []
        data = {"cursor": cursor, "has_more": True}
        while data.get("has_more"):
            data = self.rpc("files/list_folder/continue", {"cursor": data["cursor"]})
            entries += list(data.get("entries", []))
        return [e for e in entries if e.get(".tag") == "file"], data.get("cursor", cursor)

    def longpoll(self, cursor: str, timeout: int = 180) -> dict:
        """Blockiert bis zu `timeout`s, bis Dropbox Änderungen meldet.

        -> {"changes": bool, "backoff": int}. Ohne Authorization-Header
        (Cursor ist das Credential) und gegen notify.dropboxapi.com.
        """
        data = self.rpc("files/list_folder/longpoll", {"cursor": cursor, "timeout": int(timeout)},
                        base=NOTIFY, authed=False, timeout=timeout + 90)
        return {"changes": bool(data.get("changes")), "backoff": int(data.get("backoff") or 0)}

    def temporary_link(self, path: str) -> str:
        """4h gültiger Direktlink (für Download/ClickUp-Attachment in Part 2)."""
        return self.rpc("files/get_temporary_link", {"path": path}).get("link", "")

    def metadata(self, path: str) -> dict:
        return self.rpc("files/get_metadata", {"path": _api_path(path)})


# --- Helfer ----------------------------------------------------------------

def _api_path(path: str) -> str:
    """Dropbox will '' für den Root und '/Ordner' ohne Slash am Ende."""
    p = (path or "").strip()
    if p in ("", "/"):
        return ""
    return "/" + p.strip("/")


def _retry_after(exc, body: str, attempt: int) -> float:
    header = (exc.headers or {}).get("Retry-After") if hasattr(exc, "headers") else None
    if header:
        try:
            return min(float(header), 300.0)
        except ValueError:
            pass
    try:
        err = json.loads(body).get("error", {})
        hold = err.get("retry_after")
        if hold:
            return min(float(hold), 300.0)
    except Exception:
        pass
    return min(2 ** attempt, 60)


def _explain(endpoint: str, status: int, body: str) -> str:
    """Dropbox-Fehler in Klartext — spart beim Einrichten viel Rätselraten."""
    hints = {
        "path/not_found": "Der Watch-Pfad existiert in diesem Dropbox-Account nicht "
                          "(Groß/Kleinschreibung egal, aber Tippfehler/Team-Space prüfen).",
        "invalid_access_token": "Token ungültig/zurückgezogen — `dbx_watch.py auth` erneut laufen lassen.",
        "missing_scope": "Der App fehlt ein Scope. In der Dropbox-App-Console nötig: "
                         "files.metadata.read, files.content.read (+ sharing.read optional), dann neu autorisieren.",
        "no_permission": "Kein Zugriff auf diesen Namespace — bei Dropbox Business team_member_id/path_root setzen.",
        "reset": "Cursor ungültig geworden — `dbx_watch.py scan --reset-cursor` macht einen Neuaufbau.",
    }
    for needle, hint in hints.items():
        if needle in body:
            return f"{endpoint} -> {status}: {hint} ({body[:160]})"
    return f"{endpoint} -> {status}: {body[:300]}"


def client_from_config(cfg: dict) -> DropboxClient:
    """Client aus config + ENV bauen. ENV gewinnt (CI/Server ohne Secrets-Datei)."""
    d = cfg.get("dropbox", {})
    return DropboxClient(
        app_key=os.environ.get("DROPBOX_APP_KEY") or d.get("app_key", ""),
        app_secret=os.environ.get("DROPBOX_APP_SECRET") or d.get("app_secret", ""),
        refresh_token=os.environ.get("DROPBOX_REFRESH_TOKEN") or d.get("refresh_token", ""),
        access_token=os.environ.get("DROPBOX_ACCESS_TOKEN", ""),
        team_member_id=os.environ.get("DROPBOX_TEAM_MEMBER_ID") or d.get("team_member_id", ""),
        path_root=os.environ.get("DROPBOX_PATH_ROOT") or d.get("path_root", ""),
    )


def entry_to_item(entry: dict) -> dict:
    """Dropbox-File-Metadata -> schlankes Item für folders.py."""
    return {
        "path": entry.get("path_display") or entry.get("path_lower") or "",
        "name": entry.get("name", ""),
        "size": int(entry.get("size") or 0),
        "server_modified": entry.get("server_modified") or entry.get("client_modified") or "",
        "rev": entry.get("rev", ""),
        "id": entry.get("id", ""),
        "content_hash": entry.get("content_hash", ""),
    }


# --- Selftest (offline) ----------------------------------------------------

def _selftest() -> int:
    fails: list[str] = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    eq(_api_path("/"), "", "root path")
    eq(_api_path(""), "", "empty path")
    eq(_api_path("Video Upload/"), "/Video Upload", "normalized path")
    eq(_api_path("/Video Upload"), "/Video Upload", "kept path")

    v, c = pkce_pair()
    eq(len(c) >= 43, True, "challenge length")
    eq("=" in v or "=" in c, False, "no padding in pkce")
    eq(hashlib.sha256(v.encode()).digest() == base64.urlsafe_b64decode(c + "=="), True, "challenge matches verifier")
    eq("code_challenge_method=S256" in authorize_url("key", c), True, "authorize url")
    eq("token_access_type=offline" in authorize_url("key", c), True, "offline token")

    cl = DropboxClient(app_key="k", refresh_token="r", team_member_id="dbmid:42", path_root="123")
    cl._access_token, cl._expires_at = "tok", time.time() + 600
    h = cl.headers()
    eq(h["Authorization"], "Bearer tok", "bearer header")
    eq(h["Dropbox-API-Select-User"], "dbmid:42", "select-user header")
    eq(json.loads(h["Dropbox-API-Path-Root"]), {".tag": "namespace_id", "namespace_id": "123"}, "path-root header")
    eq("Authorization" in cl.headers(authed=False), False, "longpoll header unauthed")
    eq(json.loads(DropboxClient("k", "r", path_root="home").headers(False)["Dropbox-API-Path-Root"]),
       {".tag": "home"}, "home path-root")

    item = entry_to_item({".tag": "file", "name": "a.mp4", "path_display": "/V/a.mp4",
                          "size": "12", "rev": "01a", "id": "id:x",
                          "server_modified": "2026-10-13T10:00:00Z", "content_hash": "abc"})
    eq(item["size"], 12, "size cast")
    eq(item["path"], "/V/a.mp4", "path_display preferred")

    eq("files.metadata.read" in _explain("files/list_folder", 401, '{"error_summary":"missing_scope/..."}'),
       True, "scope hint")
    eq("Tippfehler" in _explain("files/list_folder", 409, '{"error_summary":"path/not_found/."}'),
       True, "not found hint")

    try:
        DropboxClient(app_key="k", refresh_token="")
        fails.append("missing token should raise")
    except DropboxError:
        pass

    for f in fails:
        print("FAIL", f)
    print(f"dbx_api selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    raise SystemExit(_selftest() if args.selftest else 0)
