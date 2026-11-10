# MPC Mapper als Mac-App bauen

Mit `build_mac.command` wird aus dem Projekt eine normale Mac-App
(`MPC Mapper.app`), die per Doppelklick startet – ohne Terminal.

## Voraussetzung (einmalig)

Python 3.9 oder neuer von <https://www.python.org/downloads/> installieren.

## App bauen

1. Diesen Ordner auf den Mac kopieren (z. B. nach „Dokumente“).
2. **Doppelklick auf `build_mac.command`.**
   - Meldet macOS „kann nicht geöffnet werden“: Rechtsklick auf die Datei →
     **Öffnen** → **Öffnen**.
   - Passiert gar nichts: Terminal öffnen, `bash ` tippen (mit Leerzeichen),
     die Datei ins Terminal ziehen, Enter.
3. Warten (beim ersten Mal 3–5 Minuten, braucht Internet), bis **„Fertig!“** erscheint.
4. Die App liegt danach im Programme-Ordner. Der Finder zeigt sie automatisch an.

Die Plugin-Dateien für das Pult liegen zusätzlich in `dist/grandMA3-Plugin`,
bereit zum Kopieren auf den USB-Stick.

## Hinweise

- Die App läuft auf dem Mac-Typ, auf dem sie gebaut wurde (Apple Silicon oder Intel).
- Beim ersten Verbinden fragt macOS, ob „MPC Mapper“ eingehende
  Netzwerkverbindungen annehmen darf: **Erlauben**, sonst kommt vom Pult kein Feedback.
- Neue Version vom Projekt? Ordner aktualisieren und `build_mac.command` erneut starten.
- Aufräumen: Die Ordner `build`, `dist` und `.venv-build` dürfen gelöscht werden.
