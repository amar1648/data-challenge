# Ansatz

Die Hinweise unter den Überschriften ersetzen. Dieser Text ist Teil der Abgabe.

## Die drei Konsumenten

Was braucht die Vergleichsansicht, was braucht der Agent, was braucht die API? Wo ist das dieselbe Struktur, und wo nur eine andere Lesart derselben Struktur?

## Harmonisiertes Modell

Welche Einheiten gibt es, wie adressiert man sie, wie hängen zwei Stände desselben Akts zusammen? Was bleibt gleich, wenn dieselbe Stelle auf Deutsch und auf Englisch gelesen wird? Die Struktur an einem kurzen Ausschnitt aus den Beispielen zeigen.

- Einheit mit sprachneutraler Adresse art-N/par-N/pt-x für alle Quellen, Quellschreibweise nur im label
- Gliederung (Abschnitte) als eigene Einheiten, aber nicht in der Adresse, damit „§ 3“ stabil bleibt, wenn sich die Gliederung ändert
- content_hash über Überschrift + Text, source_anchor zur Rückverfolgung in die Rohdatei
- Ablage pro Stand und Sprache

## Deterministisch und Sprachmodell

Wo reichen Regeln, und wo liefert ein Modell einen Mehrwert, den eine Regel nicht hergibt? Wenn du eines benutzt: welches, warum dieses, was ein Aufruf als Eingabe bekommt, und was dadurch durchsuchbar wird. Was wird bei einem neuen Stand neu gerechnet, was nicht? Kein Anbieter ist vorgegeben.

## PDF

Die Beispiele enthalten kein PDF. Beschreiben, wie ein Amtsblatt-PDF vorbereitet würde: oft ohne verlässliche Textschicht, mit Kopfzeilen, Seitenzahlen und mehreren Spalten.

## Lookup, Query, Diff

Wie beantwortest du eine Stellenangabe, die beiden Fragen und den Vergleich zweier Stände? Woran machst du fest, was in die Antwort gehört und was draußen bleibt? Der Hersteller und der Händler fallen unter denselben Akt und haben nicht dieselben Pflichten. Was folgt, wenn eine Pflicht nicht erfüllt wird? Trägt deine Struktur das?

### Query
- Regeln: Überschriften, Modalverben, „hat … zu“, Anspruch → Pflicht des Gegenübers
- Pflicht immer mit ihren Ausnahmen ausgeben (Art. 3 Abs. 3)
- Lieber „Adressat unbestimmt“ als eine Stelle weglassen (README: fehlende Stelle wiegt schwerer)
- Sanktionsnormen verlinkt (Art. 6 → Art. 3, 4, 5, 5a)

### Diff
- Paarung über die Adresse, Vergleich über den Hash, Wortdiff für geänderte Einheiten
- Normalisierung entscheidend (Fußnotenverweise hätten einen falschen Treffer erzeugt)
- ▼-Marker der EU als Gegenprobe; Befund: sie sind unvollständig (Art. 2 Nr. 2), deshalb eigener Textvergleich als Grundlage

### Evaluierung
- Goldsets mit Begründung, Bewertung nur Einheit oder Nachfahre, Textanteil als dritte Kennzahl
- Overfitting erkannt → unabhängiges Goldset (LkSG) aus separater Sitzung → hier kommen gleich die ehrlichen Zahlen

## Grenzen

Was bewusst wegfällt, und wo der Ansatz versagt.

- Unterabsätze nicht als eigene Einheiten (Art. 6 Abs. 1 erscheint als „geändert“ statt „neuer Unterabsatz“)
- Erwägungsgründe, Fußnoten, Anlagen als Textblock
- Gestrichener Text in konsolidiertem Formex

## Code starten

Abweichungen vom mitgelieferten Einstieg, und wie die vier Befehle laufen. Falls Schlüssel nötig sind: Variablenname und wofür.
