# Beispiele

Bewertet wird, was auf diesen Dateien läuft. Die vier Befehle in der [README](../README.md) sind die Mindestvorführung, an `de-burlg` und an den beiden HTML-Ständen. Die übrigen Dateien gehören zum Eingabesatz: dieselbe Struktur muss sie tragen können. Im Ansatz kurz sagen, wie.

Weitere öffentliche Texte darf man sich dazuholen. Die Abgabe muss ohne einen Live-Abruf nachvollziehbar bleiben, weil Quellen sich ändern.

## Weitere Texte holen

**Deutsche Bundesgesetze, XML.** [Gesetze im Internet](https://www.gesetze-im-internet.de/) liefert je Gesetz ein Zip. Das Muster ist `https://www.gesetze-im-internet.de/<slug>/xml.zip`, zum Beispiel [burlg/xml.zip](https://www.gesetze-im-internet.de/burlg/xml.zip). Der Slug steht in der Adresse der HTML-Ansicht des Gesetzes. Amtlicher Gesetzestext ist nach § 5 UrhG gemeinfrei.

**EU, HTML.** `https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:<CELEX>`

**EU, PDF.** Dieselbe Stelle mit `TXT/PDF` statt `TXT/HTML`. Das ist die Eingabe, die der Ansatz beschreibt und der Code nicht abdecken muss: Amtsblatt-Seiten, oft mit Kopfzeile, Seitenzahl und mehreren Spalten, manchmal ohne brauchbare Textschicht.

**EU, Formex.** Das Amtsblatt-Markup heißt Formex (`fmx4`). Es liegt nicht als direkter Link auf der EUR-Lex-Seite, sondern an der CELLAR-Schnittstelle. SPARQL-Endpoint: `https://publications.europa.eu/webapi/rdf/sparql`. Gesucht wird die Manifestation mit Typ `fmx4` zur CELEX-Nummer, Sprachcode `DEU` oder `ENG`. Die gefundene URL mit `Accept: application/zip, application/xml;type=fmx4` laden. Die Antwort ist meist ein Zip mit dem XML und, bei Anhängen, mit Bilddateien. Konsolidierte Fassungen haben eine CELEX-Nummer, die mit `0` beginnt, zum Beispiel `02023R1115-20251226`.

© Europäische Union, EUR-Lex und CELLAR. Weiterverwendung mit Quellenangabe. Konsolidierte Fassungen haben dokumentarischen Charakter und sind nicht die rechtsverbindliche Amtsblatt-Fassung.

## `de/` — Gesetze im Internet, XML

Ein Stand je Gesetz. Akt-Kennung im Prototyp: `de-` plus Dateiname ohne Endung, also `de-burlg`.

| Datei | Akt | Stand laut Datei |
|---|---|---|
| `gg.xml` | Grundgesetz | Zuletzt geändert durch Art. 1 G v. 22.3.2025 I Nr. 94 |
| `burlg.xml` | Bundesurlaubsgesetz | Zuletzt geändert durch Art. 3 Abs. 3 G v. 20.4.2013 I 868 |
| `bgb.xml` | Bürgerliches Gesetzbuch | Neugefasst durch Bek. v. 2.1.2002 I 42, 2909; 2003, 738 |
| `betrsichv_2015.xml` | Betriebssicherheitsverordnung | Zuletzt geändert durch Art. 27 G v. 18.12.2025 I Nr. 347 |
| `bimschg.xml` | Bundes-Immissionsschutzgesetz | Neugefasst durch Bek. v. 17.5.2013 I 1274; 2021, 123 |
| `hinschg.xml` | Hinweisgeberschutzgesetz | Zuletzt geändert durch Art. 2 G v. 22.7.2026 I Nr. 223 |
| `enefg.xml` | Energieeffizienzgesetz | Ausfertigung 13.11.2023 |
| `gwg_2017.xml` | Geldwäschegesetz | Zuletzt geändert durch Art. 12 Abs. 4 G v. 29.6.2026 I Nr. 197 |
| `bdsg_2018.xml` | Bundesdatenschutzgesetz | Zuletzt geändert durch Art. 3 G v. 12.5.2026 I Nr. 139 |
| `lksg.xml` | Lieferkettensorgfaltspflichtengesetz | Ausfertigung 16.7.2021 |

`de-burlg`, Paragraph 3 Absatz 1, ist das Beispiel für `lookup`.

## `eu/formex/` — Formex-Zip, Deutsch und Englisch

Dieselbe Fassung liegt zweimal bei, `*_de.fmx.zip` und `*_en.fmx.zip`. Zwei Akte haben zwei Stände. Die Dateinamen sind die CELEX-Nummern.

| Datei ohne Sprachsuffix | Akt | Stand |
|---|---|---|
| `32016R0679` | Datenschutz-Grundverordnung, Amtsblatt | 4.5.2016 |
| `02016R0679-20160504` | Dieselbe Verordnung, konsolidiert | 4.5.2016 |
| `32023R1115` | Verordnung über entwaldungsfreie Lieferketten, Amtsblatt | 9.6.2023 |
| `02023R1115-20251226` | Dieselbe Verordnung, konsolidiert | 26.12.2025 |
| `02013L0034-20260318` | Bilanzrichtlinie, konsolidiert | 18.3.2026 |
| `32021R1119` | Europäisches Klimagesetz | 9.7.2021 |
| `32022D2481` | Beschluss über das digitale Jahrzehnt | 19.12.2022 |
| `32022L2464` | Richtlinie zur Nachhaltigkeitsberichterstattung | 16.12.2022 |
| `32022L2555` | NIS-2-Richtlinie | 27.12.2022 |
| `32022R1288` | Technische Regulierungsstandards zur Offenlegungsverordnung | 25.7.2022 |
| `32023R0956` | CO2-Grenzausgleich | 16.5.2023 |
| `32024R1689` | KI-Verordnung | 12.7.2024 |

`32022R1288` ist groß. Die Anhänge liegen in der Zip als Bildseiten, nicht als Text.

## `eu/32015R2120_de.html` und `eu/02015R2120-20240515_de.html`

Dieselbe Verordnung auf Deutsch, zwei Stände, zwei HTML-Auslieferungen. Das Markup ist nicht dasselbe. Zwischen den Ständen hat sich der Text geändert.

Verordnung (EU) 2015/2120 vom 25. November 2015 über Maßnahmen zum Zugang zum offenen Internet.

| Datei | Was sie ist |
|---|---|
| `32015R2120_de.html` | Ursprüngliche Amtsblatt-Fassung, CELEX `32015R2120` |
| `02015R2120-20240515_de.html` | Konsolidierte Fassung mit Stand 15. Mai 2024, CELEX `02015R2120-20240515` |

Herkunft: [CELEX:32015R2120](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:32015R2120) und [CELEX:02015R2120-20240515](https://eur-lex.europa.eu/legal-content/DE/TXT/HTML/?uri=CELEX:02015R2120-20240515).

Artikel 7 fehlt in beiden Dateien. Er ändert nur die Verordnung (EU) Nr. 531/2012 und macht etwa die Hälfte des Originals aus. Das übrige Markup ist unverändert.
