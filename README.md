# Data Challenge: Gesetzestexte vorbereiten

Plane etwa 4 bis 6 Stunden ein.

## Kontext

sustaind baut eine globale Gesetzesdatenbank über mehr als 120 Länder. Die Texte kommen aus vielen Quellen und Formaten. Wir harmonisieren sie, damit sie danach sauber weiterverarbeitet werden können: Stände vergleichen, gezielt durchsuchen, eine einzelne Stelle abrufen.

Dabei gilt eine Maßgabe. So deterministisch und regelbasiert wie möglich. Ein KI-Modell dort, wo eine Regel nicht trägt oder wo es einen klaren Mehrwert liefert. Der typische Mehrwert in dieser Aufgabe: den Text so aufbereiten, dass er durchsuchbar wird, ohne ihn vollständig in einen Agenten zu laden.

Modelle darfst du dafür einsetzen. Welches, und an welcher Stelle, entscheidest du. Der Einstieg gibt keines vor.

## Worum es geht

Die Quellen liefern nicht dasselbe Format: mal XML mit Gliederung und Metadaten, mal HTML, mal PDF. Der Text soll so vorbereitet werden, dass drei Konsumenten ihn nutzen können, ohne dass jeder Konsument den Rohtext neu versteht.

**Vergleich in der Anwendung.** Zwei Stände desselben Akts stehen nebeneinander, und es ist sichtbar, was sich geändert hat. Abzugeben ist eine strukturierte Gegenüberstellung: alte Einheit, neue Einheit, Art der Änderung. Eine Oberfläche bauen wir daraus später selbst.

**Agent.** Aus dem vorbereiteten Text sollen sich Stellen holen lassen, die eine Frage beantworten. Die beiden Fragen für diese Aufgabe:

- Für wen gilt dieser Akt?
- Welche Pflichten ergeben sich daraus?

Der Agent soll dafür nicht den ganzen Text in den Kontext bekommen. Die Antwort sind die betroffenen Stellen, mit einer Adresse und dem Textstück.

Diese Antwort ist nur brauchbar, wenn sie die Stellen trifft, die jemand wirklich braucht. Fehlt eine relevante Stelle, handelt der Kunde oder der Agent auf einer unvollständigen Grundlage. Kommt fast der ganze Akt zurück, trägt die Frage nichts mehr.

Ein Fall, den eine flache Liste über den ganzen Akt nicht beantwortet: Jemand fällt unter den Akt, weil er Hersteller ist, jemand anderes, weil er Händler ist. Die Pflichten sind nicht dieselben. Wird eine Pflicht nicht erfüllt, kann daraus etwas folgen. Ob deine Struktur das trägt, gehört in den Ansatz.

**API.** Kundinnen und Kunden holen gezielt eine Stelle, zum Beispiel Paragraph 3 Absatz 4. Dieselbe Schnittstelle soll die beiden inhaltlichen Fragen bedienen können, nicht nur die Stellenangabe. Dieselben Kundinnen und Kunden wechseln die Sprache desselben Akts. Eine Stelle, die auf Deutsch eine Pflicht beschreibt, beschreibt auf Englisch dieselbe Pflicht. Im Repo liegen dafür bei vielen EU-Akten beide Sprachfassungen.

Lookup, Query und Diff sind drei Lesarten einer Struktur. Gliederung, die in der Quelle schon steht, liest du regelbasiert aus. Ob die beiden Fragen darüber hinaus ein Modell brauchen, begründest du im Ansatz.

Allein in Deutschland sind es über 6000 Gesetze, und sie ändern sich. Ein neuer Stand darf nicht heißen, dass unveränderter Text noch einmal genauso viel kostet. Wie die Kosten im Rahmen bleiben, gehört in den Ansatz.

## Was du abgibst

- `submission/ANSATZ.md`, ausgefüllt
- Code, der auf den beigelegten Beispielen läuft

Die Sprache ist frei. Im Repo liegt ein Python-Einstieg, damit Setup und Befehle in unter 15 Minuten stehen.

PDF kommt in der Realität vor und gehört in den Ansatz. Der Code muss es nicht verarbeiten. Amtsblätter und Portal-Exporte liegen oft ohne verlässliche Textschicht vor, mit Kopfzeilen, Seitenzahlen und mehreren Spalten.

Nicht Teil der Aufgabe: Quellen anbinden, Zeitpläne, eine Oberfläche, eine produktive API, weitere Länder.

## Beispiele

Beschreibung, Herkunft und Lizenz stehen in [`samples/README.md`](samples/README.md). Dort steht auch, wo weitere Texte liegen: Gesetze im Internet als XML, EUR-Lex als HTML oder PDF, Formex über die CELLAR-Schnittstelle.

Im Repo:

- `samples/de/`, zehn Bundesgesetze als XML, darunter `de-burlg`
- `samples/eu/formex/`, EU-Rechtsakte als Formex-Zip, Deutsch und Englisch, bei zwei Akten je zwei Stände
- `samples/eu/32015R2120_de.html` und `samples/eu/02015R2120-20240515_de.html`, dieselbe Verordnung als HTML in zwei Ständen

## Was der Prototyp kann

Der Vertrag liegt an der Kommandozeile. Die Form der Dateien unter `output/` ist Teil der Lösung und hier nicht vorgegeben.

```bash
python -m challenge prepare
python -m challenge lookup --act de-burlg --ref "§ 3 Abs. 1"
python -m challenge query --act de-burlg --question applicability
python -m challenge query --act de-burlg --question obligations
python -m challenge diff \
  --from samples/eu/32015R2120_de.html \
  --to samples/eu/02015R2120-20240515_de.html
```

- `prepare` schreibt die eigene Struktur nach `output/`.
- `lookup` gibt die genannte Stelle aus. Läuft ohne Modell.
- `query` gibt Treffer aus: Adresse und Textstück, nicht den ganzen Akt. `applicability` ist die Frage nach dem Geltungsbereich, `obligations` die Frage nach den Pflichten. Ob dafür ein Modell nötig ist und welches, steht im Ansatz. Der Stub gibt keines vor und ruft keines auf.
- `diff` gibt die strukturierte Gegenüberstellung der beiden Stände aus. Läuft ohne Modell.

Die mitgelieferten Befehle laden die Beispiele und melden, dass die Schritte noch offen sind.

## Setup

Python 3.11 oder neuer. Die Befehle im Projektordner ausführen.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Schlüssel, die die eigene Lösung braucht, kommen in eine `.env` im Projektordner. Die Datei ist ignoriert und wird nicht mit abgegeben. Name und Zweck der Variablen stehen im Ansatz.

```bash
python -m challenge --help
```

## Bewertung

- Eine Struktur trägt Lookup, Query und Diff, den Sprachwechsel und die Frage, welche Stellen in eine Antwort gehören.
- Regeln tragen, was die Quelle schon hergibt. Ein Modell ist begründet, inklusive der Stelle, an der es einen Mehrwert liefert, den eine Regel nicht hergibt. Die Kosten bleiben bei tausenden Akten und neuen Ständen nachvollziehbar.
- Stellen bleiben über die Aufbereitung hinweg adressierbar.
- Der Code läuft auf den beigelegten Dateien.
- Der Ansatz benennt Grenzen und das, was bewusst wegfällt.

Viel Erfolg.
