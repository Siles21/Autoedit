# QC-Checkliste — Prüf-Agent (jedes Video, vor Auslieferung)

Diese Liste geht der Prüf-Agent **bei jedem Video** durch — Punkt für Punkt, BEVOR Simon es sieht.
Zusammengestellt aus Broadcast-/Caption-QC-Standards + real gefundenen Bugs. Jeder Punkt nennt,
WIE geprüft wird: **[det]** = deterministisches Script · **[vis]** = visuelle Frame-Sichtung (`qc_frames.py`).

## 1 — Position & Safe-Area
- [ ] **[vis]** Kein dunkles Scrim-/Backdrop-Feld OHNE Inhalt darin (Scrim sitzt da, wo der Text ist). ← *realer Bug 20s*
- [ ] **[vis]** Text/Grafik im Title-Safe-Bereich — **nicht** in den äußeren ~5 % (nicht abgeschnitten). ← *„ganz unten"-Bug*
- [ ] **[vis]** Nicht-Takeover-Einblendungen im **unteren Drittel**, verdecken NICHT das Gesicht.
- [ ] **[vis]** Inhalt nicht durch Offset/Positionierung aus dem Bild geschoben (unten/seitlich).
- [ ] **[vis]** Takeover-Cards: Inhalt mittig, sauber zentriert.

## 2 — Lesbarkeit & Kontrast
- [ ] **[vis]** Hoher Kontrast Text↔Hintergrund — Scrim/Schatten vorhanden auf unruhigem/hellem Grund.
- [ ] **[vis]** Schriftgröße gut lesbar (auch klein gedacht / am Handy).
- [ ] **[vis]** Textfarbe hebt sich vom Hintergrund ab (nicht Bronze auf Bronze o. Ä.).

## 3 — Textinhalt & Überlauf
- [ ] **[det]** Kein Text-Overflow / Abschneiden (qc_visual long-text-Heuristik).
- [ ] **[vis]** Max. ~2 Zeilen, kurz & prägnant (nicht > ~20 % der Fläche).
- [ ] **[det]** Du-Form, keine Emojis, nur essenzielle Info.

## 4 — Timing & Sync
- [ ] **[det]** Animation erscheint, WENN das Wort gesprochen wird (Anker + Lead 0,4 s) — nicht zu spät/früh.
- [ ] **[det]** Mindeststandzeit ≥ 1,3 s pro Einblendung (zu kurz = nicht lesbar).
- [ ] **[det]** Maximale Standzeit ≤ 10 s (Einzel ≤ 4,5 s, sonst sequence).
- [ ] **[det]** Dichte: mind. alle ≤ 10 s ein Ereignis (gapcheck).

## 5 — Kollisionen & Überlappung
- [ ] **[det]** Keine zwei Overlays gleichzeitig an gleicher Position (qc_visual Kollision).
- [ ] **[det]** Takeover endet, BEVOR die nächste Animation startet (kein Card-Übergangs-Matsch).

## 6 — Rechtschreibung & Fakten
- [ ] **[det]** Namen / Komposita / Eigennamen korrekt (qc_spell, Whisper-Garbles wie „Rückhauswerte").
- [ ] **[det]** On-Screen-Zahl = gesprochene/Quell-Zahl (keine erfundenen Werte, Remi/Transkript).
- [ ] **[det]** Transkript-Fehler an on-screen-Stellen (qc_transcript MUST-FIX).
- [ ] **[det]** Lower-Third NUR für Personen (lint-lt).

## 7 — Leere / fehlende Elemente
- [ ] **[vis]** Jede geplante Animation rendert sichtbar (kein Blank/Schwarz-Frame, keine fehlende Datei).
- [ ] **[det]** Keine Orphan-/Doppel-Clips (prune); Anzahl Clips = Anzahl Plan-Einträge.

## 8 — Marken-Konsistenz
- [ ] **[vis]** Korrekte Marken-Farben, Font, Akzent durchgängig.
- [ ] **[vis]** Look einheitlich (kein Stil-Bruch zwischen Typen).

## 9 — Technik
- [ ] **[det]** Overlay-Auflösung = Video-Auflösung (4K bei 4K-Quelle), kein Mini-Overlay.
- [ ] **[det]** Alpha intakt (ProRes 4444), korrekte fps.
- [ ] **[det]** Audio: SFX vorhanden, **Peak −25 dB**, kein Clipping; Stimme nicht übertönt.
- [ ] **[det]** Dateiname-Timecode korrekt (Sequenz-fps, nicht Render-fps).

## 10 — Final-Playback (Pflicht, fängt Kontext-Fehler)
- [ ] **[vis]** Fertiges Video EINMAL in Normalgeschwindigkeit komplett ansehen — wie der Zuschauer.
      Fängt Timing-/Rhythmus-/Übergangs-Fehler, die in Einzel-Checks gut aussehen.

---
**Quellen:** Title-Safe ([Venera](https://www.veneratech.com/what-is-title-safe-and-why-it-still-matters-in-modern-video-production)),
Lower-Third-Best-Practices ([Vimeo](https://vimeo.com/blog/post/what-is-lower-thirds), [MasterClass](https://www.masterclass.com/articles/how-to-use-lower-third-graphics-in-film-and-tv)),
Caption-QC-Standards/Timing ([ClosedCaptionCreator](https://www.closedcaptioncreator.com/blog/articles/best-practices-qc-closed-captioning-broadcast.html), [DCMP](https://dcmp.org/learn/5-captioning-guidelines-for-the-dcmp), [3Play](https://www.3playmedia.com/blog/closed-captioning-subtitling-standards-in-ip-video-programming/)).
