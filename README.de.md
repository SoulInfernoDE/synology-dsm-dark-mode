# Dark Mode für DSM

[English version](README.md)

Ein echtes dunkles Design für den Desktop von Synology DSM 7, ausgeliefert als
normales DSM-Paket (ohne Root, ohne Änderungen an Systemdateien, übersteht
DSM-Updates).

- Anmeldeseite, Desktop, Taskleiste, Widgets, Systemsteuerung, Paket-Zentrum,
  File Station, Speicher-Manager, Ressourcen-Monitor, DSM-Hilfe,
  Sicherheitsberater, Support-Center und die übrigen integrierten Apps.
- **Automatisch** (folgt dem Dunkelmodus des Betriebssystems, ohne Aufblitzen
  beim Laden), **Hell** oder **Dunkel** – pro DSM-Benutzer über ein Symbol in
  der Taskleiste wählbar. Die Wahl wird in den DSM-Einstellungen des Benutzers
  gespeichert und gilt damit in jedem Browser.
- Diagramme (ECharts, z. B. Ressourcen-Monitor) werden über ihre eigenen
  Farboptionen eingefärbt, nicht mit einem Invertierungsfilter: Die Farben der
  Datenreihen bleiben erhalten.

## Funktionsweise

DSM 7 kennt keine Designs. Die neueren Komponenten (syno-vue-components)
nutzen CSS-Variablen, der größte Teil der Oberfläche ist aber ExtJS mit fest
eingetragenen Farben und grauen PNG-/SVG-Sprites für weiße Hintergründe. Ein
handgeschriebenes Design würde mit jedem DSM- oder Paket-Update brechen. Das
Paket **erzeugt** das Design deshalb auf dem NAS aus den Stylesheets, die DSM
tatsächlich lädt:

1. **Einhängepunkt:** DSM bindet die `style.css` jeder Paketoberfläche unter
   `webman/3rdparty/<Paket>/` in den `<head>` der Anmeldeseite und des
   Desktops ein. Früher kann ein Paket nicht eingreifen – noch vor dem ersten
   Zeichnen.
2. **Schatten-Kaskade:** `darkgen.py` liest alle Stylesheets in DSMs
   Ladereihenfolge und kopiert jede Regel, die eine Farbeigenschaft setzt –
   mit gleichem Selektor, dunkler Farbe und einer zusätzlichen ID-Spezifität
   (`:not(#dsmdark)`). Alle Kopien erhalten denselben Zuschlag, schlagen damit
   die Originale und behalten untereinander die ursprüngliche Kaskade
   (inklusive `!important`, Media Queries und Keyframes).
3. **Palette:** Farben werden in OKLCH je nach Rolle umgerechnet (Fläche,
   Text, Rahmen, Schatten). Grautöne werden in einen dunklen Bereich
   gespiegelt, Akzentfarben behalten ihren Farbton – DSM-Blau bleibt
   DSM-Blau. CSS-Variablen werden aufgelöst, sodass die variablenbasierten
   Komponenten dieselbe Palette bekommen.
4. **Bilder:** Oberflächen-Sprites werden eingeordnet (graues Symbol, helles
   Hintergrundbild oder farbiges Icon); nur die ersten beiden werden
   umgefärbt. Dafür gibt es einen kleinen PNG-/SVG-Codec in reinem Python
   (`darkimg.py`), weil DSM keine Bildbibliotheken mitbringt.
5. **Umschalter:** Alle dunklen Regeln stehen in einem einzigen
   `@media (prefers-color-scheme: dark)`-Block. „Automatisch“ braucht
   überhaupt kein Skript; für „Hell“/„Dunkel“ schreibt `DarkMode.core.js` die
   Bedingung dieses Blocks zur Laufzeit um.
6. **Selbstheilend:** Das Design wird beim Paketstart neu erzeugt (also auch
   nach jedem Neustart durch ein DSM-Update). Nach jeder Anmeldung fragt das
   Desktop-Skript `regen.cgi`, ob der Build aktuell ist: Ein Stylesheet mit
   neuer URL (DSM- oder Paket-Update) oder eine geänderte Datei unter gleicher
   URL (Größe und Änderungszeit stehen im Manifest) löst einen Neuaufbau aus,
   und das neue Stylesheet wird ohne Neuladen der Seite eingesetzt.
   Umgefärbte Bilder werden zwischengespeichert, ein Neuaufbau dauert etwa
   3 Sekunden.

Das helle Design bleibt völlig unverändert: Mit „Hell“ sind die berechneten
Farben aller Elemente identisch mit DSM ohne Paket.

## Update-Sicherheit und Ladereihenfolge

- DSM bietet kein Benutzer-Stylesheet und keine Design-Einstellung. Die
  persönlichen Einstellungen umfassen nur Hintergrundbild und Farben des
  Desktops, das Anmeldeportal nur Hintergrund und Logo.
- Alles unter `/usr/syno/synoman` wird von DSM-Updates ersetzt, deshalb
  schreibt das Paket dort nie. Die Paketdateien liegen in
  `/var/packages/DarkMode` (auf dem Volume); DSM legt den Link unter
  `webman/3rdparty` bei jedem Start neu an.
- Die Wahl pro Benutzer wird mit `SYNO.SDS.UserSettings` in
  `/usr/syno/etc/preference/<Benutzer>/usersettings` gespeichert, das DSM bei
  Updates behält.
- Das erzeugte Stylesheet wird im `<head>` geladen, bevor DSM irgendetwas
  zeichnet. „Automatisch“ greift deshalb schon im ersten Bild. Eine feste
  Wahl, die vom Betriebssystem abweicht, greift, sobald die Desktop-Skripte
  laufen (deutlich unter einer Sekunde).

## Getestete DSM-Versionen

| DSM | Ergebnis |
| --- | --- |
| 7.2.2-72806 (VirtualDSM) | alle Prüfungen bestanden |
| 7.4.1-90080 (VirtualDSM) | alle Prüfungen bestanden, keine Codeänderung nötig |

Prüfungen: Erzeugung auf dem NAS, Anmeldeseite, Taskleisten-Menü und Wahl pro
Benutzer, Kontrast-Audit von 14 Ansichten (9 Seiten der Systemsteuerung,
File Station, Speicher-Manager, Ressourcen-Monitor, DSM-Hilfe,
Paket-Zentrum), Diagramme, unverändertes helles Design (berechnete Farben von
8.000 Elementen verglichen), Selbstheilung nach einem geänderten
System-Stylesheet.

Was sich von 7.2.2 zu 7.4.1 geändert hat und wie das Paket damit umgeht:

- Die Ladereihenfolge der Modul-Stylesheets ist komplett anders. Der
  Generator liest die tatsächliche Reihenfolge von der Startseite, dafür ist
  keine Änderung nötig.
- Neue Modul-Stylesheets (`AutoUpdateDelayOrCancel`) und gewachsene
  (Speicher-Manager nutzt jetzt 22 statt 1 CSS-Variable, Willkommen-App,
  File Station, Systemsteuerung) werden automatisch erfasst.
- Unverändert: der Einhängepunkt über `webman/3rdparty`, alle globalen
  Design-Tokens, die vom Skript genutzten Desktop-APIs (Taskleiste,
  Benutzereinstellungen, Optionsfelder, Texte, SynoToken), ECharts 4.2.1,
  Python 3.8 und curl.

Um eine neue DSM-Version vorab zu prüfen, auf altem und neuem System die
Bestandsaufnahme ausführen und die Ergebnisse vergleichen:

```bash
sh tools/dsm-inventory.sh > inventory-<Version>.txt
```

### Zwischenspeicher-Fallen, die das Paket abfängt

DSM sendet für Paketdateien keine Cache-Header und bildet seine
Versionsparameter so, dass sie sich bei Paket-Updates nicht ändern:

- `style.css?v=` ist die Änderungszeit von `ui/config`. `build.sh` setzt sie
  neu, damit jeder Paket-Build eine neue URL bekommt.
- `DarkMode.js?v=` ist DSMs eigene Build-Nummer und ändert sich nur mit
  DSM-Updates. `DarkMode.js` ist deshalb ein kleiner, stabiler Lader, der
  `build.json` (nie zwischengespeichert) liest und `DarkMode.core.js` unter
  einer URL lädt, die sich mit jedem Build ändert.
- Ein Neuaufbau auf dem NAS behält die von DSM erzeugte URL. Das Skript
  vergleicht die Signatur im geladenen Stylesheet mit `manifest.json` und
  setzt das aktuelle ein.

## Installation

Paket bauen und im Paket-Zentrum installieren (Manuelle Installation):

```bash
./build.sh
```

Ergebnis ist `dist/DarkMode-<Version>-noarch.spk` (DSM 7.0 oder neuer, jedes
Modell). Nach dem Start erscheint in der Taskleiste ein Symbol mit einem halb
gefüllten Kreis. Wird das Paket angehalten, ist das Design aus.

## Grenzen

- Seiten außerhalb des DSM-Desktops (Synology Photos, Drive, Office und
  andere Apps in eigenen Browser-Tabs) und Inhalte von anderen Servern
  (Hilfe-Artikel von help.synology.com) werden nicht eingefärbt.
- Canvas-Zeichnungen außer ECharts und Farben, die Skripte als Inline-Styles
  setzen, behalten ihre hellen Farben.
- Eine feste Wahl („Dunkel“ bei hellem Betriebssystem) kann beim Laden kurz
  das helle Design zeigen.

## Entwicklung

```
src/lib/darkgen.py      Stylesheet-Generator (Python 3.8, nur Standardbibliothek)
src/lib/darkimg.py      PNG-/SVG-Einordnung und Umfärbung
src/share/base.css      immer aktive Regeln (Taskleisten-Symbol)
src/share/extra.css     handgeschriebene Ergänzungen im dunklen Block
src/ui/DarkMode.js      von DSM gestarteter Lader (lädt DarkMode.core.js)
src/ui/DarkMode.core.js Umschalter, Diagramme, Aktualitätsprüfung, Taskleiste
src/ui/regen.cgi        Aktualitätsprüfung und Neuaufbau (angemeldete Benutzer)
tools/dsm-inventory.sh  Bestandsaufnahme der DSM-Teile, auf die das Paket angewiesen ist
src/bin/darkmode-regen  Neuaufbau-Skript (Startseite -> Generator)
package/                SPK-Steuerdateien
```

Der Generator läuft auch auf einem PC mit einer gespeicherten DSM-Startseite:

```bash
python3 src/lib/darkgen.py --root <Kopie von /usr/syno/synoman> --index index.html --out style.css
```

## Lizenz

GPL-3.0, siehe [LICENSE](LICENSE).
