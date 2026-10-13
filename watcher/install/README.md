# Dauerbetrieb

Der Watcher ist ein langlebiger Prozess (`dbx_watch.py watch`), der per
Longpoll an Dropbox hängt. Er braucht keinen Cron — nur einen Supervisor, der
ihn nach Neustart/Absturz wieder startet.

## macOS (launchd)

```bash
cp com.autoedit.dropbox-watcher.plist.example \
   ~/Library/LaunchAgents/com.autoedit.dropbox-watcher.plist
# PFADE im plist anpassen (WorkingDirectory, python3, Logpfade)
launchctl load  ~/Library/LaunchAgents/com.autoedit.dropbox-watcher.plist
launchctl start com.autoedit.dropbox-watcher
tail -f ~/Library/Logs/autoedit-watcher.log
```

Stoppen/entfernen:
```bash
launchctl unload ~/Library/LaunchAgents/com.autoedit.dropbox-watcher.plist
```

## Linux / NAS (systemd)

```bash
sudo cp autoedit-watcher.service.example /etc/systemd/system/autoedit-watcher.service
sudo nano /etc/systemd/system/autoedit-watcher.service    # User + Pfade
sudo systemctl daemon-reload
sudo systemctl enable --now autoedit-watcher
journalctl -u autoedit-watcher -f
```

## Gesund?

```bash
python3 dbx_watch.py status      # Läufe, Cursor, wartende Ordner, Queue-Größe
tail -5 events.jsonl             # letzte ausgespielte Jobs
```

Läuft der Prozess nicht, verliert man nichts: `scan` holt beim nächsten Start
alles nach (Delta-Cursor + Ordner-Zustand liegen in `state.json`).
