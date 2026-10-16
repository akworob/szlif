# Zmiany

## 0.2.0 (październik 2026)

- **Style pisania.** Dwie nowe listy na stronie: **czytelność** (normalna, prosta, akademicka, ekspercka) i **cel tekstu** (ogólny, naukowy, biznesowy, e-mail, esej, marketingowy, prawny). W wierszu poleceń: `--czytelnosc` i `--cel`. Styl obowiązuje w każdej rundzie.
- **Strażnik pewności.** Ostrzega, gdy z akapitu znika osłabienie („może”, „nie zawsze”, „zwykle”) albo dochodzi wzmocnienie („muszą”, „zawsze”, „na pewno”).
- **Słowa bez śladu w wyniku.** Strona i raport wypisują słowa z oryginału, których nie ma w wyniku nawet w innej formie, np. pominięty element wyliczenia.
- **Aktualizacje.** `szlif.py aktualizuj` pobiera najnowszą wersję, `szlif.py --wersja` pokazuje obecną. Za zgodą Szlif raz na dobę sprawdza przy starcie, czy jest nowsza wersja, i proponuje aktualizację.
- **Instalator wznawia przerwane pobieranie modelu** (do 5 prób).
- **Błąd jednego akapitu nie zatrzymuje całości.** Akapit zostaje wtedy bez zmian, z podanym powodem. Brak serwera modelu dalej zatrzymuje przebieg.
- **Ostrzeżenie o modelach w chmurze Ollamy.** Gdy wybierzesz taki model, strona pisze, że tekst wyjdzie z komputera.
- **Samo czyszczenie znaków** przyjmuje teksty do 200 000 znaków.
- **Drobne:** zmiana samych odstępów nie jest już pokazywana jako zmiana; „tyg.” i „tydz.” to dla strażnika to samo; strona sama odświeża stan po powrocie do karty, gdy wcześniej nie było połączenia z modelem.

## 0.1.0 (październik 2026)

Pierwsza publiczna wersja: przepisywanie Bielikiem akapit po akapicie, czyszczenie ukrytych znaków, strażnik liczb, długości i komentarzy o tekście, sprawdzanie sensu Bielikiem, prompt do weryfikacji, wiersz poleceń `szlif.py przepisz`, instalator Ollamy i modelu na macOS i Windows.
