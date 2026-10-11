# Ansatz

## Die drei Konsumenten

Alle drei Konsumenten lesen dieselbe Struktur: eine Liste von Einheiten je Akt, Stand und Sprache. Jede Einheit hat eine stabile Adresse, ihren Text, einen Hash über den Inhalt und Tags aus der Anreicherung. Lookup, Query und Diff sind drei Zugriffe auf diese Daten, keine drei eigenen Datenmodelle.

- **Vergleichsansicht:** Sie braucht die Einheiten zweier Stände, die sich über die Adresse einander zuordnen lassen, dazu die Art der Änderung und den geänderten Wortlaut. Lesart: Zusammenführen zweier Stände über die Adresse, Vergleich über den Hash.
- **Agent:** Er braucht kleine, adressierte Textstücke mit Rolle (Geltungsbereich, Pflicht, Sanktion) und Adressat, damit er nur das Relevante in den Kontext lädt und nicht den ganzen Akt. Lesart: Filter über die Tags.
- **API:** Sie muss eine Stellenangabe wie „§ 3 Absatz 1“ oder „Artikel 10 Absatz 5“ auf eine Adresse abbilden und die Sprachfassung wählen können. Lesart: direkter Zugriff über die Adresse. Die beiden inhaltlichen Fragen bedient sie über dieselben Tags wie der Agent, in jeder Sprachfassung.

## Harmonisiertes Modell

**Einheiten.** Ein Akt besteht aus Einheiten der Typen Gliederung (Teil, Abschnitt, Titel), Artikel beziehungsweise Paragraph, Absatz, Satz (nur wenn ein Absatz mehrere Listen mit neu beginnender Nummerierung enthält), Nummer beziehungsweise Buchstabe, Eingangsformel, Präambel und Anlage. Jede Einheit trägt:

- `address`: eine sprachneutrale Adresse, die aus der Gliederung abgeleitet wird, für alle Quellen in derselben Form: `art-3/par-1/pt-a`. Deutsche Paragraphen werden ebenfalls als `art` adressiert. Die Schreibweise der Quelle („§ 3“, „Artikel 3“, „Article 3“, „(1)“, „1.“) steht nur im `label`.
- `heading`, `text`: Überschrift und der eigene Text der Einheit, ohne den Text ihrer Kinder.
- `parent`, `order`: Eltern-Einheit und Position im Akt.
- `content_hash`: SHA-256 über Überschrift und Text mit normalisiertem Leerraum.
- `source_anchor`: die Stelle in der Rohdatei, zum Beispiel die `doknr` aus Gesetze im Internet oder die Artikel-ID im HTML, damit jede Einheit zur Quelle zurückverfolgt werden kann.
- `refs`: Verweise auf andere Stellen im selben Akt.
- `tags`: Ergebnisse der Anreicherung (Rolle, Adressaten mit ihrer Herkunft, Sanktionsverweise, Änderungsakt).

**Gliederung.** Teile und Abschnitte sind eigene Einheiten und Eltern der Paragraphen, gehören aber nicht zur Adresse. „§ 3“ wird ohne Abschnitt zitiert und bleibt adressierbar, wenn sich die Gliederung ändert.

**Adressen werden abgeleitet, nicht übernommen.** Die IDs im HTML von EUR-Lex sind dafür nicht verlässlich: In Artikel 8 der Amtsblatt-Fassung von 2015/2120 trägt ein zitierter Fremdtext die ID `001.003`, die sonst Artikel 1 Absatz 3 bezeichnen würde, und zwischen den beiden HTML-Ständen gibt es keine gemeinsamen Absatz-IDs. Die Adresse entsteht deshalb aus der Artikelnummer und der normalisierten Absatznummer. Paragraphen mit nur einem, unnummerierten Absatz bekommen trotzdem `par-1`, damit „§ 1 Absatz 1“ auflösbar ist.

**Stände und Sprachen.** Gespeichert wird je Werk, Stand und Sprache: `output/<work_id>/<version>_<language>.json`. Zwei Stände sind zwei Dateien desselben `work_id`; dieselbe Adresse bezeichnet in beiden dieselbe Stelle. Die deutsche und die englische Fassung teilen sich die Adressen, weil die Gliederung identisch ist und nur die Nummernschreibweise abweicht („(1)“ gegenüber „1.“, „a)“ gegenüber „(a)“). In Formex ist das schon in der Quelle angelegt: Die Attribute `IDENTIFIER` sind in beiden Sprachen gleich.

Geprüft an der Datenschutz-Grundverordnung (32016R0679) in Formex: Beide Sprachfassungen ergeben exakt dieselben 903 Einheiten mit denselben Adressen, Typen, Eltern und derselben Reihenfolge. Als inhaltliche Gegenprobe wurde die Textlänge je Adresse verglichen; der einzige Ausreißer ist echt („die Landesverteidigung“ gegenüber „defence“). `lookup --act eu-2016-679 --ref "Article 6(1)(f)" --lang en` liefert dieselbe Stelle wie „Art. 6 Abs. 1 Buchst. f“ auf Deutsch. Die Tags der deutschen Fassung werden über die Adresse auf die englische übertragen, aber nur, wenn beide Fassungen exakt dieselben Adressen haben. Eine Pflicht, die auf Deutsch erkannt wurde, ist so auch auf Englisch dieselbe Pflicht, ohne zweite Anreicherung.

**Version.** Für deutsche Gesetze gilt das Datum aus der Standangabe, sonst das der Neufassung, sonst das der Ausfertigung. Das Exportdatum (`builddate`) wird bewusst nicht verwendet, weil es sich bei jedem Export ändert, ohne dass sich der Rechtsstand ändert.

**Beispiel**, Bundesurlaubsgesetz § 3 Absatz 1:

```json
{
  "address": "art-3/par-1",
  "label": "(1)",
  "type": "paragraph",
  "heading": null,
  "text": "Der Urlaub beträgt jährlich mindestens 24 Werktage.",
  "parent": "art-3",
  "content_hash": "sha256:…",
  "source_anchor": "BJNR000020963BJNE000401308:P[1]",
  "refs": [],
  "tags": { "model": { … } }
}
```

## Deterministisch und Sprachmodell

**Regeln tragen alles, was die Quelle schon hergibt:** Gliederung, Adressen, Verweise im selben Akt, Lookup, Diff und das Erkennen von Pflichten und Geltungsbereich. Die Regeln für Pflichten erkennen Modalverben („muss“, „darf nicht“), die Form „hat … zu“, „ist verpflichtet“, Ansprüche als Pflicht des Gegenübers und Pflichtsätze im Präsens mit einem Akteur als Subjekt. Den Geltungsbereich erkennen sie über Überschriften (Anwendungsbereich, Geltungsbereich, Begriffsbestimmungen) und typische Formulierungen.

**Wo die Regeln versagen, hat die Messung gezeigt** (Einzelheiten unter Evaluierung). Auf dem unabhängigen Testset zum Lieferkettensorgfaltspflichtengesetz finden die Regeln Pflichten noch zu 85 Prozent, ohne einen einzigen falschen Treffer. Den Adressaten bestimmen sie aber in keinem Fall richtig, weil ihre Wortlisten aus dem Bundesurlaubsgesetz und der Verordnung 2015/2120 stammen und im Zweifel „Arbeitgeber“ einsetzen. Wer verpflichtet ist, ist eine Frage des Satzverständnisses, nicht des Wortlauts. Dort habe ich ein Modell eingesetzt und gemessen, ob es den Mehrwert tatsächlich liefert.

**Modell.** Im Prototyp läuft qwen3:4b lokal über Ollama: ohne Kosten, ohne dass Text das Haus verlässt, und reproduzierbar. Der Denkmodus ist aus, die Ausgabe wird über ein JSON-Schema erzwungen.

- **Eingabe pro Aufruf:** Titel des Akts, Überschrift des Paragraphen beziehungsweise Artikels, Label und Text der Einheit, Einleitungstext der Eltern-Einheit.
- **Ausgabe:** Rolle (Geltungsbereich, Pflicht, keine), Adressaten mit Typ (Normadressat oder Behörde), ob der Adressat im Satz steht, Art der Pflicht.

**Ergebnis der Messung.** Ich habe das Modell auf alle 314 Texteinheiten der drei Akte mit Goldset angewendet und mehrere Arten des Zusammenspiels aus demselben Ergebnis ausgewertet.

- **Als Klassifikator für die Rolle ist das kleine Modell unbrauchbar.** Es nennt fast jede Einheit eine Pflicht, im Lieferkettengesetz 198 von 212. Sein Recall von 100 Prozent entsteht nur dadurch, dass es 90 bis 96 Prozent des Akts zurückgibt, also genau den Fall „fast der ganze Akt“. Gegenstands- und Definitionsnormen hält es meist für Pflichten.
- **Als Erkenner des Adressaten auf einem unbekannten Gesetz ist es stark:** Im Lieferkettengesetz erkennt es „Unternehmen“, wo die Regeln „Arbeitgeber“ raten.
- **Sein typischer Fehler:** Es nennt den Begünstigten statt des Verpflichteten, im Bundesurlaubsgesetz zum Beispiel „Arbeitnehmer“, wo aus dem Anspruch des Arbeitnehmers die Pflicht des Arbeitgebers folgt.

**Daraus folgt die Arbeitsteilung, die jetzt Standard ist:** Die Rolle kommt aus den Regeln. Jeder Adressat trägt seine Herkunft (`via`): im Satz genannt, Gegenüber eines Anspruchs, vorherrschender Akteur des Artikels, Ersatzwert des Akts oder unbestimmt. Das Modell ersetzt nur Adressaten, die die Regel rät (Ersatzwert des Akts) oder nicht findet (unbestimmt). Adressaten, die die Regel herleitet, bleiben. Ergebnis: Im Lieferkettengesetz steigt der Anteil richtiger Adressaten von 0 auf 96 Prozent, in der Verordnung 2015/2120 bleibt er bei 100 Prozent, im Bundesurlaubsgesetz sinkt er von 94 auf 89 Prozent (eine Stelle, § 10 Absatz 1, an der der Ersatzwert richtig war und das Modell den Begünstigten wählt). Recall und Precision ändern sich nicht, weil die Rolle weiter aus den Regeln kommt.

**Was dadurch durchsuchbar wird:** Pflichten je Adressat über alle Akte hinweg, also zum Beispiel „alle Pflichten von Unternehmen“ oder „alle Pflichten von Herstellern“, ohne dass der Agent einen Akt lesen muss.

**Kosten und neue Stände.** Die Anreicherung läuft beim `prepare`, nicht bei jeder Anfrage. Ihr Ergebnis wird je Einheit gespeichert, unter einem Schlüssel aus dem Hash der vollständigen Eingabe, dem Modell und der Version des Prompts. Bei einem neuen Stand wird deshalb nur neu gerechnet, was sich an der Eingabe einer Einheit geändert hat; im Vergleich der beiden Stände von 2015/2120 sind das alle 62 Texteinheiten der neuen Fassung, weil sich der Titel des Akts geändert hat und er Teil der Eingabe ist. Bei gleichem Titel wären es 28, bei einer reinen Datumsänderung in einer Einheit ohne Unterpunkte eine einzige. Die englische Fassung muss nicht eigens angereichert werden, die Tags gelten über die gemeinsame Adresse.

Voller Lauf über die drei Akte: 314 Aufrufe in 26 Minuten auf der CPU, zusammen 202.763 Tokens Eingabe und 18.338 Tokens Ausgabe, also im Mittel rund 650 und 58 pro Aufruf. Ein zweiter Lauf kam ohne einen einzigen neuen Aufruf aus. Rund 450 der 650 Eingabe-Tokens sind der gleichbleibende Systemprompt; mehrere Einheiten pro Aufruf zu bündeln oder Prompt-Caching eines Anbieters zu nutzen, senkt die Kosten deutlich. Grobe Hochrechnung: Die zehn deutschen Beispielgesetze haben zusammen rund 14.000 Einheiten, ohne das Bürgerliche Gesetzbuch etwa 540 pro Gesetz. Für 6.000 Gesetze sind das einige Millionen Einheiten. Weil das Modell nur noch für Adressaten gebraucht wird, die die Regeln nicht herleiten, geht davon nur ein Teil zum Modell; einmalig ist das eine Größenordnung von höchstens ein bis drei Milliarden Tokens, danach fallen nur Kosten für geänderte Einheiten an.

**Nächste Schritte beim Modell:** ein stärkeres gehostetes Modell mit derselben Schnittstelle, ein Prompt mit Beispielen gegen die Verwechslung von Begünstigtem und Verpflichtetem, und beides gemessen an einem weiteren unabhängigen Gesetz, nicht am Lieferkettengesetz, das jetzt als Testset verbraucht ist.

## PDF

Grundsatz: Ein PDF ist die letzte Wahl. Gibt es für denselben Akt Formex, XML oder HTML, wird diese Quelle genommen. Sonst:

1. **Textschicht prüfen.** Fehlt sie oder ist sie unbrauchbar (Zeichensalat, sehr wenig Text pro Seite), Texterkennung (OCR) mit Tesseract beziehungsweise ocrmypdf in der Sprache des Dokuments.
2. **Layout rekonstruieren.** Wortpositionen auslesen, Spalten über die x-Koordinaten trennen und spaltenweise lesen.
3. **Kopf- und Fußzeilen entfernen.** Zeilen, die auf vielen Seiten an derselben Position wiederkehren („Amtsblatt der Europäischen Union L 310/1“), und Seitenzahlen.
4. **Silbentrennung** am Zeilenende zusammenfügen.
5. **Gliederung mit denselben Mustern wie beim HTML erkennen** („Artikel N“, „(N)“, „a)“) und auf dasselbe Modell abbilden. Ab hier unterscheidet sich ein PDF für Lookup, Query und Diff nicht mehr von den anderen Quellen.
6. **Qualität prüfen.** Die Zahl der Artikel gegen das Inhaltsverzeichnis oder die andere Sprachfassung abgleichen und unsichere Einheiten markieren. Sobald eine strukturierte Fassung erscheint, gegen sie vergleichen.

Die Texterkennung kostet nur Rechenzeit und wird pro Hash der Datei gespeichert.

## Lookup, Query, Diff

### Lookup

Die Stellenangabe wird über Regeln in eine Adresse übersetzt. Verstanden werden Varianten wie „§ 3 Abs. 1“, „§3Abs.1“, „§ 3 Absatz 1“, „Art. 10 Abs. 5“, „§ 5 Abs. 1 Buchst. c“, „Article 6(1)(f)“, „Satz N“ und die Adresse selbst. Ausgegeben werden die Einheit mit ihren Kindern, Überschrift, Stand und Quellanker. Es gilt immer der neueste Stand, die Sprache wählt `--lang`. Lookup läuft ohne Modell.

### Query

Query liest nur die Tags, die beim `prepare` geschrieben wurden, und gibt Treffer mit Adresse, Label, Textstück, Begründung und Adressat aus, nicht den ganzen Akt.

- **Was in die Antwort gehört:** die Einheit, die die Pflicht oder den Geltungsbereich trägt, und zwar vollständig mit ihren Ausnahmen. Artikel 3 Absatz 3 der Verordnung 2015/2120 verbietet unterschiedliche Behandlung von Datenverkehr und erlaubt im selben Absatz Ausnahmen (Buchstaben a bis c). Eine Pflicht ohne ihre Ausnahmen wäre für einen Kunden irreführend. Listenpunkte werden nur dann angehängt, wenn der Pflichtsatz in sie hinein weiterläuft.
- **Was draußen bleibt:** Einheiten ohne Rolle. Der Anteil des zurückgegebenen Texts am Akt ist eine eigene Kennzahl (siehe Evaluierung).
- **Lieber unbestimmt als weggelassen:** Eine Pflicht, deren Adressat sich nicht bestimmen lässt, wird mit dem Adressaten „unbestimmt“ ausgegeben. Eine fehlende relevante Stelle wiegt schwerer als ein unsicherer Adressat.

**Hersteller und Händler.** Jede Pflicht trägt ihre Adressaten mit Typ (Normadressat oder Behörde) und Herkunft. Query gruppiert die Pflichten nach Adressat, Normadressaten zuerst. Dass zwei Gruppen unter denselben Akt fallen und verschiedene Pflichten haben, bildet die Struktur deshalb direkt ab. In den Beispielen: Im Bundesurlaubsgesetz Arbeitgeber, Arbeitnehmer sowie Auftraggeber und Zwischenmeister in der Heimarbeit; in der Verordnung 2015/2120 Anbieter von Internetzugangsdiensten, Anbieter öffentlicher elektronischer Kommunikation, Regulierungsbehörden, Kommission und Mitgliedstaaten. Steht im Wortlaut „einschließlich der Internetzugangsanbieter“, bekommt eine Pflicht beide Anbieter als Adressaten.

**Was folgt, wenn eine Pflicht nicht erfüllt wird.** Sanktionsnormen werden über ihre Verweise mit den Pflichten verknüpft. Artikel 6 der Verordnung 2015/2120 verweist auf die Artikel 3, 4, 5 und 5a; jede Pflicht in diesen Artikeln zeigt deshalb an, dass ein Verstoß nach Artikel 6 sanktioniert wird. Das Bundesurlaubsgesetz enthält keine Bußgeldvorschrift; im Lieferkettensorgfaltspflichtengesetz stehen die Folgen in §§ 22 und 24, werden aber noch nicht verknüpft, weil § 24 anders formuliert ist („Ordnungswidrig handelt, wer … entgegen § …“) und die Verweisregel nur „Verstöße gegen …“ erkennt.

### Diff

Die Einheiten zweier Stände werden über die Adresse einander zugeordnet und über den Hash verglichen. Ergebnis ist eine Liste mit alter Einheit, neuer Einheit und Art der Änderung (`unchanged`, `modified`, `added`, `removed`), bei geänderten Einheiten mit den eingefügten und gelöschten Textstücken. Das JSON geht auf die Standardausgabe, eine deutsche Zusammenfassung auf die Fehlerausgabe. Diff läuft ohne Modell.

Ergebnis für 2015/2120, Amtsblatt-Fassung gegen konsolidierte Fassung vom 15.05.2024: 42 unverändert, 2 geändert, 28 neu, 2 entfallen. Neu sind unter anderem Artikel 1 Absatz 3, Artikel 5a und 5b und Artikel 10 Absatz 5, entfallen ist Artikel 8. Zu jeder neuen oder geänderten Einheit wird, soweit die konsolidierte Fassung sie markiert, festgehalten, durch welchen Änderungsakt sie geändert wurde.

- **Normalisierung ist entscheidend.** Ohne das Entfernen von Fußnotenverweisen wäre Artikel 10 Absatz 4 als geändert gemeldet worden, weil dieselbe Fußnote im Original „(12)“ und in der konsolidierten Fassung „(5)“ heißt.
- **Eigener Textvergleich statt Vertrauen in die Quelle.** Die Änderungsmarkierungen (▼) der konsolidierten Fassung dienen in einem Test als Gegenprobe: Jede neue oder geänderte Einheit muss unter einer Markierung liegen, jede markierte Einheit muss neu oder geändert sein. Dabei zeigte sich, dass die Markierungen unvollständig sind: Artikel 2 Nummer 2 endet in der neuen Fassung auf „bietet;“ statt „bietet.“, weil dahinter neue Begriffe eingefügt wurden, ohne Markierung. Der Hash-Vergleich hat das gefunden.

### Evaluierung

Für die beiden Fragen gibt es drei Goldsets mit Begründung und Zitat je Eintrag: Bundesurlaubsgesetz, Verordnung 2015/2120 (Stand 2024) und Lieferkettensorgfaltspflichtengesetz §§ 1 bis 10. Sie wurden mit einem Sprachmodell vorgeschlagen und von mir stichprobenartig gegen den Wortlaut geprüft. Grenzfälle sind eigens markiert und werden nicht gewertet.

- **Treffer** zählen nur, wenn sie die Gold-Einheit selbst oder einer ihrer Nachfahren sind. Ein ganzer Artikel als Antwort zählt nicht als Treffer für seine Absätze, sonst ließe sich der Recall durch grobe Antworten künstlich erhöhen.
- **Kennzahlen:** Recall, Precision nach Einheiten und nach Zeichen (die Zählung nach Einheiten hängt von der Feinheit der Zerlegung ab), Anteil des zurückgegebenen Texts am Akt und Anteil richtig bestimmter Adressaten.
- **Überanpassung erkannt.** Die Regeln wurden am Bundesurlaubsgesetz und an der Verordnung entwickelt und erreichen dort 95 bis 100 Prozent. Diese Zahlen sind nicht übertragbar. Deshalb wurde ein drittes Goldset in einer getrennten Sitzung erstellt, die die Regeln nicht kannte, und die Regeln wurden darauf ohne weitere Anpassung gemessen.

Pflichten (Standard ist „Regeln mit Modell-Adressat“):

| Akt | Lesart | Recall | Precision Einheiten / Zeichen | Textanteil | Adressat richtig |
|---|---|---|---|---|---|
| Bundesurlaubsgesetz | nur Regeln | 95 % | 100 % / 100 % | 57 % | 94 % |
| Bundesurlaubsgesetz | Regeln mit Modell-Adressat | 95 % | 100 % / 100 % | 57 % | 89 % |
| Verordnung 2015/2120 | nur Regeln | 96 % | 100 % / 100 % | 66 % | 100 % |
| Verordnung 2015/2120 | Regeln mit Modell-Adressat | 96 % | 100 % / 100 % | 66 % | 100 % |
| **Lieferkettengesetz (unabhängig)** | nur Regeln | 85 % | 100 % / 100 % | 38 % | **0 %** |
| **Lieferkettengesetz (unabhängig)** | Regeln mit Modell-Adressat | 85 % | 100 % / 100 % | 38 % | **96 %** |
| Lieferkettengesetz (unabhängig) | nur Modell | 100 % | 81 % / 85 % | 96 % | 96 % |

Geltungsbereich (in beiden Standard-Lesarten gleich):

| Akt | Recall | Precision Einheiten / Zeichen | Textanteil |
|---|---|---|---|
| Bundesurlaubsgesetz | 100 % | 100 % / 100 % | 7 % |
| Verordnung 2015/2120 | 100 % | 100 % / 100 % | 12 % |
| **Lieferkettengesetz (unabhängig)** | 100 % | **16 % / 10 %** | 46 % |

Das Modell allein erreicht beim Geltungsbereich nur 33 bis 40 Prozent Recall. Beim Lieferkettengesetz versagt also auch die Standard-Lesart beim Geltungsbereich: Die Überschriftenregel nimmt alles unter „Begriffsbestimmungen“, dort werden aber Risiken definiert und nicht die Verpflichteten. Der hohe Textanteil bei Pflichten liegt daran, dass die drei Akte fast nur aus Pflichten bestehen.

Verfehlte Pflichten, an denen die Regeln scheitern: Sätze ohne Pflichtformulierung („Der Urlaub beträgt jährlich mindestens 24 Werktage“), Pflichten im Indikativ ohne bekannten Akteur („Das Unternehmen legt eine Verfahrensordnung … fest“), Infinitive, die erst in den Listenpunkten stehen, und Pflichten, die sich nur aus dem Zusammenhang ergeben (Artikel 5a Absatz 3 der Verordnung).

## Grenzen

**Bewusst weggelassen**
- Erwägungsgründe, Schlussformel, Unterschriften und Titel der EU-Akte. Erwägungsgründe haben keine bindende Wirkung, und die konsolidierte Fassung enthält sie nicht.
- Fußnoten. Sie enthalten vor allem Text- und Änderungsnachweise.
- Anlagen werden als ein Textblock gespeichert, Tabellen als Text in der Form „Zelle | Zelle“.
- Satz als eigene Ebene gibt es nur, wenn ein Absatz mehrere Listen mit neu beginnender Nummerierung enthält.
- Formex ist nur für die Datenschutz-Grundverordnung umgesetzt, um den Sprachwechsel zu zeigen. In konsolidiertem Formex steht gestrichener Text innerhalb der Markierung DELETED noch in der Datei und müsste vor dem Parsen entfernt werden.
- Die Modell-Anreicherung läuft nur für die drei Akte mit Goldset.

**Wo der Ansatz versagt**
- Unterabsätze sind keine eigenen Einheiten. Ein neu eingefügter Unterabsatz erscheint im Diff deshalb als Änderung des Absatzes (Artikel 6 Absatz 1 der Verordnung), nicht als neue Einheit.
- Text nach einer Liste steht am Ende des Absatzes, und bei Absätzen mit Satzsegmenten gibt Lookup einen Satz ohne Liste vor den Sätzen mit Liste aus.
- Verweise: Bereiche wie „§§ 4 bis 6“, relative Verweise wie „Absatz 1 Buchstabe c“ und Verweise auf andere Gesetze werden nicht aufgelöst. Artikel 83 der Datenschutz-Grundverordnung („Verstöße gegen die folgenden Bestimmungen … Artikel 8, 11, 25 bis 39“) wird deshalb nicht mit den Pflichten verknüpft.
- Die Wortlisten der Regeln sind auf die Entwicklungsakte zugeschnitten. In der Datenschutz-Grundverordnung bleibt der Adressat „Verantwortlicher“ unbestimmt, weil er nicht in der Wortliste steht und dieser Akt nicht angereichert wurde.
- Die Regeln sind deutsch. Die englische Fassung bekommt ihre Tags nur über die Übertragung; der Beleg einer Regel bleibt dabei deutsch.
- Das Modell (qwen3:4b, Prompt Version 1) taugt nicht als Klassifikator für die Rolle und verwechselt Begünstigte mit Verpflichteten. Der Prompt wurde bewusst nicht am Testset nachgeschärft.
- Die enge Variante des Zusammenspiels (das Modell ersetzt nur geratene Adressaten) habe ich festgelegt, nachdem die erste, breitere Variante auf allen drei Goldsets gemessen war, also mit Kenntnis des Testsets. Sie folgt einer allgemeinen Regel (Herleitungen bleiben, Vermutungen werden ersetzt) und ist nicht auf einzelne Stellen zugeschnitten; die Zahlen des Lieferkettengesetzes sind dadurch trotzdem etwas weniger unabhängig.
- Die Goldsets sind klein und von einem Sprachmodell vorgeschlagen. Bei der Erstellung des unabhängigen Goldsets war das Tag einer einzigen Einheit (§ 1 Absatz 1, Geltungsbereich) kurz sichtbar.

## Code starten

Setup wie im mitgelieferten Einstieg, ohne zusätzliche Pakete. Die Befehle aus der README laufen unverändert:

```
python -m challenge prepare
python -m challenge lookup --act de-burlg --ref "§ 3 Abs. 1"
python -m challenge query --act de-burlg --question applicability
python -m challenge query --act de-burlg --question obligations
python -m challenge diff --from samples/eu/32015R2120_de.html --to samples/eu/02015R2120-20240515_de.html
```

- **Keine Schlüssel, kein Netz nötig.** `prepare` übernimmt die Modellergebnisse aus dem mitgelieferten Cache `enrichment/cache.json`, ohne das Modell aufzurufen. Das Protokoll des Laufs liegt in `enrichment/run-v1.log`.
- **Modell neu befragen** (nur für Einheiten, die im Cache fehlen): `python -m challenge prepare --enrich`, mit einem erreichbaren Ollama. Variablen: `OLLAMA_URL` (Adresse des Ollama-Servers, Standard `http://host.docker.internal:11434`) und `LLM_MODEL` (Standard `qwen3:4b`).
- **Weitere Akte und Sprachen:** `--act eu-2015-2120`, `--act de-lksg`, `--act eu-2016-679` und die übrigen deutschen Gesetze; die Sprachfassung mit `--lang en`, zum Beispiel `python -m challenge query --act eu-2016-679 --lang en --question obligations`.
- **Lesart von Query:** `--mode`, Standard `hybrid` (Regeln mit Modell-Adressat). Zum Vergleich `rules`, `hybrid-wide`, `combined` und `model`.
- **Auswertung gegen die Goldsets:** `python -m challenge.evaluate`
- **Tests:** `python -m unittest discover -s tests -t .`