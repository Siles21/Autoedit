"""lib — Bausteine des Dropbox-Watchers (Part 1 der Video-Automation).

Reine Logik (classify, folders) ist dependency-frei und per --selftest testbar.
IO-Module: dbx_api (HTTPS via urllib), state (JSON-Store), emit (Queue + Hook).
"""
