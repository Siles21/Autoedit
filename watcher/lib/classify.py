#!/usr/bin/env python3
"""classify.py — Dateityp-Erkennung + Berater-Zuordnung für den Dropbox-Watcher.

Reine Funktionen, keine Deps, kein Netz. Entscheidet pro Datei:
Video? Transkript? Skript (Text+PDF-Paar)? Rohmaterial-Beiwerk? Müll (ignore)?
Und pro Pfad: welcher Berater hat das hochgeladen (aus der Ordnerstruktur).

    python3 classify.py --selftest
"""
from __future__ import annotations

import argparse
import posixpath
import re
import unicodedata

# --- Kinds ------------------------------------------------------------------
# video      : Schnitt-Quellmaterial (das, was den Job auslöst)
# transcript : fertiges Transkript (SRT/VTT/words.json/..._transkript.txt)
# script     : gesprochenes Skript / Drehbuch (Text + PDF, s. script_confidence)
# pdf/text   : unklassifizierte Dokumente (werden zu script-Kandidaten verrechnet)
# audio, image, project, other, ignore
VIDEO_EXT = {
    "mp4", "mov", "m4v", "mxf", "avi", "mkv", "mts", "m2ts", "mpg", "mpeg",
    "webm", "wmv", "braw", "r3d", "insv", "lrv", "avchd", "3gp",
}
AUDIO_EXT = {"wav", "mp3", "m4a", "aac", "aiff", "aif", "flac", "ogg", "opus", "wma"}
SUBTITLE_EXT = {"srt", "vtt", "sbv", "ass", "ssa"}
TEXT_EXT = {"txt", "md", "markdown", "rtf", "doc", "docx", "pages", "odt"}
IMAGE_EXT = {"jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "webp", "gif", "psd", "ai"}
PROJECT_EXT = {"prproj", "aep", "drp", "fcpxml", "xml", "aaf", "edl", "veg"}
DATA_EXT = {"json", "csv", "yaml", "yml"}

# Betriebssystem-/Dropbox-Müll und halbfertige Uploads.
IGNORE_EXT = {"dbtemp", "part", "partial", "crdownload", "download", "tmp", "temp", "lock"}
IGNORE_NAMES = {
    ".ds_store", "thumbs.db", "desktop.ini", "icon\r", "icon", ".dropbox",
    ".dropbox.attr", ".localized", ".gitkeep",
}
IGNORE_PATTERNS = (
    re.compile(r"^\._"),                        # macOS AppleDouble
    re.compile(r"^~\$"),                        # Office-Lockfiles
    re.compile(r"conflicted copy", re.I),       # Dropbox-Konflikte
    re.compile(r"\(in Konflikt stehende Kopie", re.I),
)

# Namens-Hinweise. Reihenfolge = Priorität (erster Treffer gewinnt).
TRANSCRIPT_HINTS = (
    "transcript", "transkript", "transkription", "transcription", "words",
    "untertitel", "subtitle", "captions", "timecodes",
)
SCRIPT_HINTS = (
    "skript", "script", "drehbuch", "teleprompter", "sprechtext", "vorlage",
    "konzept", "hook", "reeltext", "reel-text",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _fold(value: str) -> str:
    """Kleinschreibung + Umlaute/Akzente entfernt — für robustes Matching."""
    norm = unicodedata.normalize("NFKD", value or "")
    norm = norm.replace("ß", "ss")
    norm = "".join(ch for ch in norm if not unicodedata.combining(ch))
    return norm.lower()


def slug(value: str) -> str:
    """'Thorben Müller / Reel 02' -> 'thorben-muller-reel-02'."""
    return _SLUG_RE.sub("-", _fold(value)).strip("-")


def ext_of(name: str) -> str:
    return posixpath.splitext(name)[1].lstrip(".").lower()


def stem_of(name: str) -> str:
    return posixpath.splitext(name)[0]


def is_ignored(name: str) -> bool:
    """Müll, Lockfiles, halbfertige Uploads, Dropbox-Konfliktkopien."""
    low = (name or "").lower()
    if not low or low in IGNORE_NAMES or low.startswith(".~"):
        return True
    if ext_of(name) in IGNORE_EXT:
        return True
    return any(p.search(name) for p in IGNORE_PATTERNS)


def _has_hint(name: str, hints: tuple[str, ...]) -> bool:
    folded = _fold(stem_of(name))
    return any(h in folded for h in hints)


def classify_file(name: str) -> str:
    """Dateiname -> kind. Siehe Kind-Liste oben."""
    if is_ignored(name):
        return "ignore"
    ext = ext_of(name)
    if ext in VIDEO_EXT:
        return "video"
    if ext in SUBTITLE_EXT:
        return "transcript"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in IMAGE_EXT:
        return "image"
    if ext in PROJECT_EXT:
        return "project"
    if ext == "pdf":
        # Ein PDF mit Transkript-Namen ist ein Transkript, sonst Dokument.
        return "transcript" if _has_hint(name, TRANSCRIPT_HINTS) else "pdf"
    if ext in TEXT_EXT or ext in DATA_EXT:
        if _has_hint(name, TRANSCRIPT_HINTS):
            return "transcript"
        if _has_hint(name, SCRIPT_HINTS):
            return "script"
        return "text" if ext in TEXT_EXT else "other"
    return "other"


def script_confidence(kinds_with_names: list[tuple[str, str]]) -> str:
    """Wie sicher liegt im Ordner das gesprochene Skript?

    Regel vom Auftraggeber: "wenn im Ordner eine Text- und eine PDF-Datei
    drinnen ist, ist es sehr wahrscheinlich, dass das das Skript ist".

    high   : explizit als Skript benanntes Dokument ODER Text+PDF mit gleichem Stamm
    medium : Text+PDF im Ordner (ohne Namensgleichheit) — die Paar-Heuristik
    low    : nur ein Dokument (Text ODER PDF) ohne Namenshinweis
    none   : kein Dokument
    """
    texts = [n for k, n in kinds_with_names if k == "text"]
    pdfs = [n for k, n in kinds_with_names if k == "pdf"]
    named = [n for k, n in kinds_with_names if k == "script"]
    if named:
        return "high"
    if texts and pdfs:
        stems = {slug(stem_of(n)) for n in texts} & {slug(stem_of(n)) for n in pdfs}
        return "high" if stems else "medium"
    if texts or pdfs:
        return "low"
    return "none"


def path_segments(path: str) -> list[str]:
    return [seg for seg in (path or "").split("/") if seg]


def resolve_consultant(path: str, consultants: list[dict], default_id: str = "_triage") -> dict:
    """Berater aus dem Dropbox-Pfad ableiten.

    Matching-Reihenfolge (spezifisch -> unscharf):
      1. path_prefix : Eintrag hat "path" und der Ordner liegt darunter
      2. segment     : ein Pfadsegment entspricht genau einem Alias/Slug
      3. substring   : ein Alias kommt irgendwo im Pfad vor
      4. default     : Zwischenordner / Triage (Mensch oder Part 2 entscheidet)

    Rückgabe: {"id","name","matched_by","matched_on","clickup",...} — der
    komplette Consultant-Eintrag plus Match-Metadaten (nachvollziehbar im Job).
    """
    folded_path = _fold(path or "")
    segs = path_segments(path)
    folded_segs = [_fold(s) for s in segs]
    slug_segs = [slug(s) for s in segs]

    def hit(entry: dict, how: str, on: str) -> dict:
        out = dict(entry)
        out.setdefault("id", slug(entry.get("name", "")) or default_id)
        out.setdefault("name", entry.get("id", ""))
        out["matched_by"] = how
        out["matched_on"] = on
        return out

    for entry in consultants:
        prefix = _fold(entry.get("path") or "")
        if prefix:
            prefix = prefix.rstrip("/")
            if folded_path == prefix or folded_path.startswith(prefix + "/"):
                return hit(entry, "path_prefix", entry["path"])

    for entry in consultants:
        for alias in _aliases(entry):
            a_folded, a_slug = _fold(alias), slug(alias)
            if a_folded in folded_segs or (a_slug and a_slug in slug_segs):
                return hit(entry, "segment", alias)

    for entry in consultants:
        for alias in _aliases(entry):
            a_folded = _fold(alias)
            if a_folded and a_folded in folded_path:
                return hit(entry, "substring", alias)

    return {"id": default_id, "name": "Nicht zugeordnet", "matched_by": "default",
            "matched_on": "", "clickup": {}}


def _aliases(entry: dict) -> list[str]:
    out = [entry.get("id", ""), entry.get("name", "")]
    out += list(entry.get("aliases") or [])
    return [a for a in out if a]


# --- Selftest ---------------------------------------------------------------

def _selftest() -> int:
    fails: list[str] = []

    def eq(got, want, label):
        if got != want:
            fails.append(f"{label}: got {got!r}, want {want!r}")

    eq(classify_file("Reel_01.MP4"), "video", "video upper ext")
    eq(classify_file("a.mov"), "video", "mov")
    eq(classify_file("clip.braw"), "video", "braw")
    eq(classify_file("clip.mp4.dbtemp"), "ignore", "dropbox temp")
    eq(classify_file(".DS_Store"), "ignore", "ds_store")
    eq(classify_file("._Reel.mp4"), "ignore", "appledouble")
    eq(classify_file("Reel (conflicted copy).mp4"), "ignore", "conflict")
    eq(classify_file("~$Skript.docx"), "ignore", "office lock")
    eq(classify_file("Reel_01.srt"), "transcript", "srt")
    eq(classify_file("reel_transkript.txt"), "transcript", "transkript hint")
    eq(classify_file("Transcript.pdf"), "transcript", "transcript pdf")
    eq(classify_file("words.json"), "transcript", "words.json")
    eq(classify_file("Skript Reel 01.docx"), "script", "script hint")
    eq(classify_file("Notizen.txt"), "text", "plain text")
    eq(classify_file("Onepager.pdf"), "pdf", "plain pdf")
    eq(classify_file("vo.wav"), "audio", "wav")
    eq(classify_file("thumb.jpg"), "image", "jpg")
    eq(classify_file("cut.prproj"), "project", "prproj")
    eq(classify_file("random.bin"), "other", "other")

    pairs = [("video", "a.mp4"), ("text", "Reel 01.txt"), ("pdf", "Reel 01.pdf")]
    eq(script_confidence(pairs), "high", "txt+pdf same stem")
    eq(script_confidence([("text", "Notizen.txt"), ("pdf", "Vertrag.pdf")]), "medium", "txt+pdf differing")
    eq(script_confidence([("script", "Skript.docx")]), "high", "named script")
    eq(script_confidence([("text", "Notizen.txt")]), "low", "text only")
    eq(script_confidence([("video", "a.mp4")]), "none", "no docs")

    consultants = [
        {"id": "thorben", "name": "Thorben Müller", "path": "/Video Upload/Thorben",
         "aliases": ["TM"], "clickup": {"list_id": "1"}},
        {"id": "simon", "name": "Simon", "aliases": ["Si"], "clickup": {"list_id": "2"}},
    ]
    r = resolve_consultant("/Video Upload/Thorben/Reel 01", consultants)
    eq((r["id"], r["matched_by"]), ("thorben", "path_prefix"), "prefix match")
    r = resolve_consultant("/Uploads/Simon/Shoot", consultants)
    eq((r["id"], r["matched_by"]), ("simon", "segment"), "segment match")
    r = resolve_consultant("/Uploads/thorben-mueller-reels/x", consultants)
    eq(r["id"], "thorben", "fuzzy umlaut/substring match")
    r = resolve_consultant("/Uploads/Fremder/x", consultants)
    eq((r["id"], r["matched_by"]), ("_triage", "default"), "fallback triage")

    eq(slug("Thorben Müller / Reel 02"), "thorben-muller-reel-02", "slug")

    for f in fails:
        print("FAIL", f)
    print(f"classify selftest: {'OK' if not fails else str(len(fails)) + ' failures'}")
    return 1 if fails else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--name", help="einen Dateinamen klassifizieren")
    args = ap.parse_args()
    if args.name:
        print(classify_file(args.name))
    raise SystemExit(_selftest() if args.selftest else 0)
