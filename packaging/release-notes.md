## MPC Mapper für macOS und Windows

Steuert grandMA3 mit einem **Akai APC mini mk2** und/oder einem **Behringer X-Touch Compact**, inklusive LED-Rückmeldung.

### Neu in v2.0
- **Behringer X-Touch Compact**: Tasten, Drehregler und Fader belegen wie beim APC. Tasten-LEDs zeigen den Executor-Zustand, **Motorfader und LED-Kränze folgen dem Pult** (bei „Fader Master“), ohne gegen deine Hand zu arbeiten. *Neu und noch nicht am echten Gerät erprobt – bitte einmal den Gerätetest machen.*
- **Gerätetest** (Seite „Device test“): prüft bei APC und X-Touch alle Lämpchen, Motorfader, LED-Kränze und jedes Bedienelement. Während des Tests geht nichts ans Pult.
- Verbindungsleiste mit einer Zeile pro Controller; die passende Ausgangs-Schnittstelle wird automatisch gewählt.

### Welche Datei brauche ich?
Du brauchst nur **ein Komplettpaket**. Darin ist alles: das Programm, das Plugin fürs Pult, die Anleitung und ein Demo-Layout.

| Datei | Für |
| --- | --- |
| **MPC-Mapper-Windows.zip** | Windows 10 und 11 (64 Bit) |
| **MPC-Mapper-macOS-apple-silicon.zip** | Macs mit M1, M2, M3 oder M4 |
| **MPC-Mapper-macOS-intel.zip** | ältere Macs mit Intel-Prozessor |
| grandMA3-Plugin.zip | nur das Plugin fürs Pult (steckt auch in jedem Komplettpaket) |
| Anleitung.html | ausführliche Anleitung auf Deutsch (steckt auch in jedem Komplettpaket) |
| Demo-Layout.json | Beispiel-Belegung (steckt auch in jedem Komplettpaket) |

Welchen Mac du hast, steht unter  → „Über diesen Mac“ bei „Chip“ bzw. „Prozessor“.

### Windows in 4 Schritten
1. ZIP herunterladen, **Rechtsklick → „Alle extrahieren…“** (nicht direkt aus der ZIP starten).
2. Im entpackten Ordner **`MPC Mapper.exe`** doppelklicken.
3. Erscheint „Der Computer wurde durch Windows geschützt“: **„Weitere Informationen“ → „Trotzdem ausführen“**.
4. Fragt die Windows-Firewall nach Netzwerkzugriff: **Zugriff zulassen**.

### Mac in 4 Schritten
1. ZIP herunterladen und doppelklicken.
2. `MPC Mapper.app` in den Ordner **Programme** ziehen.
3. App starten. Blockiert macOS sie: **Systemeinstellungen → Datenschutz & Sicherheit** → ganz unten **„Dennoch öffnen“**.
4. Fragt macOS nach eingehenden Netzwerkverbindungen: **Erlauben**.

### Danach (beide Systeme)
- **Pult einrichten:** Ordner `gma3_library` aus `grandMA3-Plugin` auf einen USB-Stick kopieren, Plugin importieren und starten, zwei OSC-Lines anlegen (siehe `LIESMICH.txt` bzw. `Anleitung.html`).
- **Verbinden:** In MPC Mapper die IP des Pults eintragen und bei grandMA3 auf **Connect** klicken.

Original-Projekt: https://github.com/miles-p/MPC_Mapper
