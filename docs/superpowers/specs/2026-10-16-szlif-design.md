# Szlif: projekt (2026-10-16)

Szlif to lokalne narzędzie do wygładzania polskiego tekstu modelem Bielik, z porównaniem „przed / po” na stronie w przeglądarce i z czyszczeniem ukrytych znaków.

Status: **zaakceptowany przez użytkownika 2026-10-16.** Decyzje użytkownika są oznaczone **[ustalone]**, decyzje projektanta **[moja decyzja]**. Po akceptacji wszystkie są wiążące dla planu. Resztę zostawiam wykonawcy.

## 1. Po co i dla kogo

- **Dla kogo:** osoby piszące po polsku, które umieją uruchomić komendę w terminalu na macOS albo Windows. **[ustalone]**
- **Po co:** wygładzić sztywny tekst, np. szkic napisany z pomocą AI albo własny tekst w urzędowym stylu, tak żeby tekst nie wychodził z komputera.
- **Dlaczego porównanie jest sednem:** przepisywanie przez lokalny model potrafi zmienić sens. W testach autora na własnych tekstach mniej więcej 1 na 6 przepisanych akapitów zmienił fakt: jednostkę, liczbę odczytaną jako coś innego albo założenie podane jako fakt. Widok obok siebie i ostrzeżenia o liczbach są po to, żeby człowiek przeczytał każdą zmianę, zanim użyje wyniku.

## 2. Cele, nie-cele, anty-cele

**Cele**
1. Przepisywanie polskiego tekstu Bielikiem w 1, 2 albo 3 rundach. **[ustalone]**
2. Czyszczenie ukrytych znaków, z każdą zmianą widoczną w porównaniu. **[ustalone]**
3. Lokalna strona: wklejasz tekst, przetwarzasz i widzisz dwie kolumny, przed i po, z zaznaczonymi zmianami (układ A). **[ustalone]**
4. Działanie na macOS i Windows, a instalacja to Python plus jedna komenda. **[ustalone]**
5. Instalator, który sam instaluje Ollamę i pobiera Bielika, pytając t/n przed każdą zmianą w systemie. **[ustalone]**
6. Możliwość wskazania zewnętrznego serwera z modelem: Ollama na innym komputerze albo serwer w standardzie OpenAI. **[ustalone]**
7. README po polsku z krótkim akapitem po angielsku na górze, z krokami dla macOS i Windows i ze zrzutami ekranu z macOS. **[ustalone]**

**Nie-cele (nie w v1)**
- Tekst angielski i inne języki. **[ustalone]**
- Style „czytelność” i „cel”. **[ustalone, v2]**
- Paczki (pip, exe, formuła brew), oficjalne wsparcie Linuksa (może działać, ale bez obietnic), logowanie użytkowników, historia tekstów.
- Zrzuty ekranu z Windows. Dla Windows są tylko kroki opisane tekstem. **[ustalone]**

**Anty-cele (porażka, nawet jeśli działa)**
- Jakikolwiek ślad firmy, klientów, wewnętrznych ścieżek czy wewnętrznych danych autora w repo albo w historii gita. Przykłady są wyłącznie wymyślone.
- Obietnica, że Szlif oszuka detektory AI albo usunie statystyczne („matematyczne”) znaki wodne. Funkcje nazywają się wprost: **„przepisywanie Bielikiem”** i **„czyszczenie ukrytych znaków”**, nigdy „usuwanie znaków wodnych AI”. **[ustalone]**
- Tekst, który po cichu wychodzi poza komputer.
- Klucz API zapisany w pliku, w repo albo w kodzie strony.
- Zależności spoza biblioteki standardowej Pythona, CDN-y i telemetria. Strona działa bez internetu.
- Zapisywanie wklejanych tekstów na dysk albo do logów.

## 3. Ograniczenia

- **Python 3.9+, tylko biblioteka standardowa.** 3.9 to wersja, którą macOS dostarcza z narzędziami Xcode (3.9.6). Nie wolno więc używać `match` ani składni typów `X | Y` w czasie działania programu. **[moja decyzja]**
- **macOS i Windows.** Na Windows komenda to `py szlif.py`. Konsola Windows musi poprawnie wypisywać polskie znaki: przestawić strumienie na UTF-8.
- **Licencja MIT. [ustalone]** Właściciel praw w LICENSE: `akworob` (nazwa konta na GitHubie). **[moja decyzja, do zmiany przez użytkownika]**
- **Atrybucja w pliku `NOTICE` i w README:**
  - lynote-ai/humanize-text, MIT, Copyright (c) 2026 Lynote.ai. Wolno zaadaptować pomysł trzech rund z ich „Method 2” (rytm zdań, słownictwo, przejścia). Prompty piszemy od nowa po polsku, nie kopiujemy ich kodu. Do NOTICE trafia pełna nota MIT. Wersja źródła: commit `768d3048632b44c7c18c0ec64427ca04bc2f9c84`.
  - Bielik (SpeakLeash), Apache-2.0. Modelu nie dystrybuujemy, użytkownik pobiera go sam. Dodajemy notkę, że projekt nie jest związany z SpeakLeash.
  - Ollama, MIT. Tylko wzmianka; Ollama jest zewnętrznym programem.
- **Autor commitów.** Każdy commit ma autora `Marek Borowka <8522814+akworob@users.noreply.github.com>`, czyli adres noreply GitHuba, a nie prywatny e-mail. Ustawić w `git config` lokalnie dla repo, przed pierwszym commitem. **[moja decyzja]**
- **Repo `akworob/szlif`, najpierw prywatne. [ustalone]** Założenie repo i każdy push czekają na wyraźne „tak” użytkownika z nazwą, kontem i widocznością. Przed pushem trzeba przeskanować całe drzewo i historię pod kątem zakazanych nazw z sekcji 2 i pokazać wynik. Upublicznienie to osobne „tak”.
- **Lista zakazanych nazw.**
  - Lista leży w prywatnym pliku **poza repo**, bo sama zawiera te nazwy. Wykonawca dostaje ścieżkę do niej poza repo. Nie trafia ona do `.gitignore`, kodu ani historii.
  - Skan sprawdza wszystkie wersje wszystkich plików w historii, opisy commitów, nazwy i e-maile autora oraz committera, nazwy plików i metadane obrazków (EXIF, bloki tekstowe PNG).
  - Każdy zrzut ekranu przed commitem trzeba jeszcze obejrzeć.
  - Wielkość liter nie ma znaczenia; sprawdzamy też warianty bez polskich liter.

## 4. Jak to działa

### 4.1 Uruchamianie

```
python3 szlif.py                      # macOS: serwer na 127.0.0.1, otwiera przeglądarkę
py szlif.py                           # Windows
python3 szlif.py --serwer http://192.168.1.20:11434   # Ollama na innym komputerze
python3 szlif.py --serwer https://example.org/v1       # serwer w standardzie OpenAI
python3 szlif.py --model hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M
python3 szlif.py instaluj             # instalator (4.6)
```

- Serwer jest zbudowany na `http.server` (wątkowy) i słucha **wyłącznie na 127.0.0.1**. Jeśli port domyślny jest zajęty, wybiera wolny. Otwiera przeglądarkę modułem `webbrowser`, a flaga pozwala tego nie robić.
- Adres serwera modelu podaje się **tylko w wierszu poleceń** (`--serwer`) albo w zmiennej środowiskowej. Strona nie może go zmienić, bo inaczej dowolna strona w internecie mogłaby kierować ruch. **[moja decyzja]**
- Ochrona lokalnego serwera:
  - odrzucać żądania, których nagłówek `Host` nie jest adresem `127.0.0.1`/`localhost` z naszym portem (chroni przed DNS rebinding);
  - odrzucać żądania z obcym nagłówkiem `Origin`;
  - przyjmować tylko JSON.

  Bez tego obca strona mogłaby wysyłać teksty przez Szlif, a przy zewnętrznym serwerze użyć klucza API użytkownika. **[moja decyzja]**
- Jedna strona HTML z wbudowanym CSS i JS, bez bibliotek z sieci.

### 4.2 Serwer modelu

- **Domyślnie lokalna Ollama** pod `http://127.0.0.1:11434`.
- **Rozpoznawanie rodzaju serwera:** jeśli odpowiada API Ollamy (np. `/api/version`), używamy go; w przeciwnym razie zakładamy standard OpenAI (`/v1/models`, `/v1/chat/completions`). Flaga pozwala wymusić rodzaj. **[moja decyzja]**
- **Ścieżka Ollama** (`/api/chat`):
  - temperatura 0.3;
  - jawny kontekst `num_ctx` 16384;
  - bez cichego obcinania promptu: w Ollamie są do tego opcje, które trzeba sprawdzić w wersji, na której testujemy;
  - przycięta odpowiedź (`done_reason` ≠ `stop`) daje ostrzeżenie.
- **Ścieżka OpenAI** (`/v1/chat/completions`):
  - klucz tylko ze zmiennej `SZLIF_API_KEY`, wysyłany jako `Authorization: Bearer`;
  - `finish_reason == "length"` daje ostrzeżenie;
  - kontekstu nie da się tu wymusić, więc README mówi, żeby długi tekst dzielić na części.
- **Lista modeli** na stronie pochodzi z `/api/tags` albo `/v1/models`. Domyślny model to ten, który wybrał instalator, albo `--model`.
- **Funkcje chmurowe Ollamy:** dla lokalnej Ollamy odczytujemy `/api/status`. Jeśli funkcje chmurowe nie są wyłączone, strona pokazuje żółte ostrzeżenie z instrukcją. Nie blokujemy działania. **[moja decyzja]**
- **Serwer spoza tego komputera:** gdy adres nie jest pętlą zwrotną, strona pokazuje stały **czerwony pasek**: „Tekst jest wysyłany do: <adres>, poza ten komputer”.
- **Komunikaty błędów** są po polsku i mówią, co zrobić, np. „Ollama nie działa. Uruchom: …”, „Brak modelu. Uruchom: python3 szlif.py instaluj”.

### 4.3 Strona (układ A) [ustalone]

- **U góry:** pole na tekst i jeden pasek opcji:
  - tryb: prosty / standardowy / wzmocniony, czyli 1 / 2 / 3 rundy, domyślnie standardowy;
  - ☑ „czyść ukryte znaki” (domyślnie włączone);
  - ☐ „myślniki → przecinki” (domyślnie wyłączone);
  - lista modeli;
  - przycisk **Przetwórz**;
  - przycisk **Tylko wyczyść znaki**, który działa bez modelu i natychmiast.
- **W trakcie:** widać postęp („runda 1 z 2…”) i można przerwać.
- **Wynik:** dwie kolumny, po lewej **Przed** (oryginał w surowej postaci), po prawej **Po**.
  - Porównanie po słowach: usunięte na czerwono i przekreślone w kolumnie Przed, dodane na zielono w kolumnie Po.
  - Każda zmiana z czyszczenia jest pomarańczową etykietą w miejscu znaku, np. `ZWSP`, `NBSP`, `BOM`, `homoglif а→a`, `— → ,`.
  - Akapity zachowane.
- **Nad kolumnami pasek podsumowania:**
  - ile znaków wyczyszczono, według rodzaju;
  - żółte ostrzeżenia strażnika (4.5): „brakuje w wyniku: 9 kwietnia”, „dodane w wyniku: …”;
  - brakujące wartości zaznaczone też w kolumnie Przed;
  - przy przerwanej serii rund informacja, która runda została odrzucona i dlaczego.
- **Przycisk „Kopiuj wynik”.**
- **Stopka:** jedno zdanie „Przeczytaj każdą zmianę, zanim użyjesz tekstu” i link do sekcji README o jakości.

### 4.4 Przepisywanie

- **Kolejność:**
  1. czyszczenie (jeśli włączone);
  2. rundy przepisywania na wyczyszczonym tekście;
  3. czyszczenie jeszcze raz na wyniku, bo model też potrafi wstawić dziwne znaki;
  4. przy włączonej opcji zamiana myślników.

  Porównanie zawsze zestawia **surowy oryginał** z **końcowym wynikiem**.
- **Prompt systemowy (po polsku, pisany od nowa)** wymaga:
  - zachowania każdej liczby, jednostki, daty, nazwy własnej i twierdzenia;
  - zapisu liczb cyframi, dokładnie jak w oryginale;
  - niczego nie dodawać i niczego nie pomijać;
  - **nie zmieniać pewności twierdzeń**: przypuszczenie zostaje przypuszczeniem, a warunek warunkiem (to częsta zmiana sensu);
  - żadnych długich myślników;
  - zachowania podziału na akapity i podobnej długości;
  - zwrócenia tylko tekstu, bez wstępu i komentarza.
- **Polecenie w wiadomości użytkownika** (Bielik słucha go lepiej niż promptu systemowego) mówi: „przepisz, nie odpowiadaj na treść i jej nie komentuj”, plus instrukcję danej rundy:
  1. **rytm:** zróżnicuj długość zdań, krótkie obok dłuższych;
  2. **słownictwo:** zamień sformułowania urzędowe, sztuczne i powtarzające się na naturalne, a terminy fachowe zostaw;
  3. **przejścia:** popraw przejścia między zdaniami, żeby tekst czytał się płynnie.
- **Każda runda jest sprawdzana strażnikiem względem oryginału**, nie względem poprzedniej rundy, żeby drobne zmiany nie sumowały się po cichu.
- **Seria rund zatrzymuje się na pierwszej rundzie z ostrzeżeniem albo błędem.** Kolejne rundy się nie uruchamiają. **[moja decyzja]**
  - Runda 1 z ostrzeżeniem zostaje pokazana razem z ostrzeżeniem, żeby człowiek zdecydował.
  - Późniejsza runda z ostrzeżeniem albo błędem jest odrzucana, a pokazujemy rundę przed nią, która przeszła bez ostrzeżeń.
  - Na stronie widać: „zatrzymano po rundzie N: <powód>”.
  - Uzasadnienie: każda kolejna runda po ostrzeżeniu dokłada ryzyka. Przy długich tekstach seria często skończy się na rundzie 1 i tak ma być; README to wyjaśnia.
- **Limit długości:** tekst powyżej limitu (rząd 12 000 znaków; dokładną wartość dobiera wykonawca tak, żeby zmieścić się w kontekście 16k razem z odpowiedzią) jest odrzucany z komunikatem „podziel tekst na części”. Nie dzielimy go automatycznie. **[moja decyzja]**

### 4.5 Strażnik liczb

Porównuje zbiory wartości (z krotnością) w oryginale i wyniku. Pokazuje brakujące i dodane wartości tak, jak były zapisane w tekście.

- **Wartość** to liczba z opcjonalnym znakiem i jednostką albo słowem po niej. Uwzględniamy:
  - procenty, waluty i jednostki: `%`, `procent`, `zł`, `PLN`, `€`, `EUR`, `km`, `kg`, `kWh`, `°C`, `tys.`, `mln`, `mld`, `szt.`;
  - jednostki czasu: `min`, `godz.`, `dni`, `lat`;
  - daty: `9 kwietnia`, `12.03.2026`, `2026-03-12`;
  - godziny: `14:30`.
- **Co liczy się jako jednostka:** tylko jednostki i słowa z listy wyżej (z polskimi odmianami: `zł`/`złotych`, `minut`/`minuty`, `lat`/`lata`, nazwy miesięcy w dopełniaczu) oraz „symboliczne” tokeny tuż po liczbie, czyli zawierające wielką literę, cyfrę albo symbol, ale niebędące zwykłym wyrazem pisanym wielką literą (`kWh`, `MWp`, `°C`, `CO2`). **Dowolny rzeczownik po liczbie nie jest jednostką.** Zmiana „5 osób → 5 rodzin” przejdzie bez ostrzeżenia, bo łapie ją dopiero człowiek. Inaczej zwykłe przeformułowania i odmiana („w 3 krokach → w 3 etapach”) dawałyby ciągłe fałszywe alarmy. **[moja decyzja]**
- **Równoważne zapisy:** `1 000` = `1000`, `12,5 %` = `12,5 procent`, `15 zł` = `15 PLN` = `15 złotych`, `30 min` = `30 minut`. `9 kwietnia` ≠ `9 maja`.
- **Każda inna zmiana zapisu daje ostrzeżenie**, nawet jeśli wartość jest ta sama: `2,5 mln` → `2 500 000`, `12,5` → `12.5`, `12.03.2026` → `12 marca 2026`. Prompt każe przepisywać liczby dokładnie, więc taka zmiana i tak jest warta oka. Lepszy fałszywy alarm niż przeoczenie. **[moja decyzja]**
- **Numeracja list** (`1.` lub `2)` na początku wiersza) nie jest wartością.
- **Dodatkowe ostrzeżenia:**
  - wynik znacznie dłuższy od tekstu (powyżej 3× liczby słów + 8): może to odpowiedź, a nie przepisanie;
  - przycięta odpowiedź;
  - pusta odpowiedź (to jest błąd).
- **Czego strażnik NIE sprawdza** (README mówi to wprost): nazw, twierdzeń, zamienionych miejscami wartości, liczb zapisanych słowami ani zmiany pewności zdania. Te rzeczy wyłapuje tylko człowiek.

### 4.6 Czyszczenie ukrytych znaków

Każda zmiana jest zapisywana z pozycją i rodzajem i trafia do porównania. Czyszczenie działa na oryginale przed przepisaniem i na wyniku po nim.

1. **Usuwane znaki niewidoczne:**
   - U+200B ZWSP, U+200C ZWNJ, U+2060 WJ, U+FEFF BOM, U+180E;
   - U+00AD miękki dywiz;
   - sterowanie kierunkiem: U+200E/U+200F, U+202A–U+202E, U+2066–U+2069;
   - znaki „tag” U+E0000–U+E007F (używane do ukrywania tekstu).

   Wyjątek: U+200D ZWJ i znaki „tag” zostają, gdy są częścią sekwencji emoji. Selektory wariantu U+FE0E/U+FE0F zostają.
2. **Nietypowe spacje zamieniane na zwykłą spację:**
   - U+00A0 NBSP, U+202F wąska NBSP, U+2007, U+2009, U+200A, U+2002–U+2006, U+205F, U+3000, U+1680.

   NBSP też, choć Word wstawia ją celowo przy „sierotkach”. Każda zamiana jest widoczna, a README to wyjaśnia. **[moja decyzja]**
3. **Separatory U+2028/U+2029** zamieniane na znak nowej linii.
4. **Homoglify:**
   - litera cyrylicy lub greki, która wygląda jak łacińska, **wewnątrz słowa mieszanego** (zawierającego też litery łacińskie) zamieniana na łacińską, np. `а`→`a`, `о`→`o`, `е`→`e`, `р`→`p`, `с`→`c`, `ο`→`o`;
   - słowa w całości cyrylickie lub greckie zostają bez zmian;
   - litery i cyfry pełnej szerokości (U+FF01–U+FF5E) zamieniane na ASCII.
5. **Opcja „myślniki → przecinki”** (domyślnie wyłączona):
   - `—` lub `–` otoczone spacjami w zdaniu zamieniane na przecinek;
   - `–` między liczbami (zakres `10–20`) zamieniane na `-`.

   Polskie cudzysłowy „ ” i wielokropek zostają.

To czyszczenie usuwa tylko **znaki**, nie statystyczny znak wodny. README mówi to wprost (sekcja 5).

### 4.7 Instalator: `python3 szlif.py instaluj` [ustalone: instaluje sam, pyta t/n]

Kroki. Przed każdą zmianą w systemie instalator pyta t/n, a po odmowie wypisuje komendę do ręcznego uruchomienia.

1. **Sprawdź Pythona i system.**
2. **Sprawdź Ollamę.** Jeśli jej nie ma:
   - **macOS z Homebrew:** `brew install ollama`;
   - **macOS bez Homebrew:** wypisz link do pobrania Ollamy ze strony ollama.com i zakończ z prośbą o ponowne uruchomienie instalatora;
   - **Windows:** `winget install -e --id Ollama.Ollama`;
   - **brak winget:** wypisz link.
3. **Uruchom Ollamę, jeśli nie działa.** Na macOS z brew przez `brew services start ollama`; aplikacja Ollama, Windows i reszta przypadków to decyzja wykonawcy. Instalator kończy się działającą Ollamą albo jasnym komunikatem, co zrobić.
4. **Funkcje chmurowe.** Zaproponuj wpis `"disable_ollama_cloud": true` w `~/.ollama/server.json`: dopisać do istniejącego JSON-a, nie nadpisywać pliku. Potem restart Ollamy i sprawdzenie przez `/api/status`.
5. **Dobór modelu do pamięci RAM:**

   | RAM | model | rozmiar |
   |---|---|---|
   | ≥ 24 GB | `hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q6_K` | 9,2 GB |
   | 12–24 GB | `…:Q4_K_M` | 6,7 GB |
   | < 12 GB | `hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0` | 5,1 GB |

   Model 4.5B ma notkę, że jakość jest niższa. Użytkownik może wybrać inny. RAM odczytujemy biblioteką standardową: `sysctl` na macOS, `ctypes` na Windows. **[moja decyzja]**
6. **Pobierz model** przez `/api/pull` z paskiem postępu, pokazując wcześniej rozmiar.
7. **Test:** przepisanie jednego zdania. Instalator zapamiętuje wybrany model w małym pliku konfiguracyjnym użytkownika (nie w repo), żeby `szlif.py` startował z nim domyślnie, i wypisuje „Gotowe. Uruchom: …”.

Instalator nie instaluje Pythona; to krok w README. Wszystko pobierane jest wyłącznie z oficjalnych źródeł: Homebrew, winget, repo SpeakLeash na Hugging Face przez Ollamę.

## 5. README (po polsku, na górze akapit po angielsku) [ustalone]

Sekcje:

1. Co to jest i co robi: dwie funkcje nazwane wprost.
2. Czego NIE robi.
3. Szybki start na macOS (zrzuty ekranu).
4. Szybki start na Windows (tylko tekst, w tym instalacja Pythona: `winget install -e --id Python.Python.3.13` albo python.org).
5. Jak czytać wynik.
6. Zewnętrzny serwer, z ostrzeżeniem o prywatności i kluczem w `SZLIF_API_KEY`.
7. **Jakość: uczciwie.** Mniej więcej 1 na 6 akapitów w testach autora zmienił fakt; strażnik nie widzi nazw ani twierdzeń.
8. **Znaki wodne i AI Act:**
   - przepisanie innym modelem najpewniej osłabia statystyczny znak wodny, ale tego nie mierzymy i nie obiecujemy, bo detektory dostawców nie są publiczne;
   - obowiązek oznaczania z art. 50 ust. 2 AI Act (od 2 sierpnia 2026, dla systemów już obecnych na rynku do 2 grudnia 2026) ciąży na dostawcy modelu;
   - art. 50 ust. 4: kto publikuje tekst z AI, żeby informować opinię publiczną w sprawach interesu publicznego, musi to ujawnić, chyba że tekst przeszedł rzetelną redakcję człowieka, który bierze za niego odpowiedzialność; Bielik też jest AI;
   - to nie jest porada prawna; podajemy linki do źródeł.
9. Prywatność: lokalnie, czerwony pasek przy zewnętrznym serwerze, funkcje chmurowe Ollamy.
10. Wymagania: RAM i dysk, tabela z 4.7.
11. Licencja i podziękowania.

Zrzuty ekranu z macOS w `docs/zrzuty/`: strona z wklejonym tekstem i wynik z etykietami i ostrzeżeniem. Robimy je na prawdziwym Bieliku, na wymyślonym przykładzie. Wynik instalatora pokazujemy jako blok tekstu, nie zrzut.

## 6. Testy i sprawdzenie

- **`unittest` z biblioteki standardowej**, cały kod logiki w Pythonie. Strona tylko wyświetla to, co policzy serwer. **[moja decyzja]** Testy obejmują:
  - czyszczenie: każda klasa znaków, emoji z ZWJ nienaruszone, homoglif tylko w słowie mieszanym;
  - strażnika: przykłady z 4.5;
  - porównanie;
  - rozpoznanie rodzaju serwera i rundy z odrzuceniem, na sztucznym serwerze z `http.server` w wątku;
  - ochronę `Host`/`Origin`;
  - logikę instalatora (wybór komend i modelu) z atrapami, bez instalowania czegokolwiek.
- **CI na GitHub Actions** (prywatne repo): `macos-latest` i `windows-latest`, Python 3.9 i 3.13. Testy jednostkowe plus próbny start serwera bez Ollamy (strona się ładuje, „Tylko wyczyść znaki” działa). To jedyne automatyczne sprawdzenie Windows, bo tu nie ma maszyny z Windows. **[moja decyzja]**
- **Ręcznie na macOS:** pełny przebieg z prawdziwym Bielikiem i zrzuty ekranu.
- Instalatora na czystym Windows nie da się tu sprawdzić. README to uczciwie zaznacza.
- **Przed każdym pushem:** skan drzewa i historii gita pod kątem zakazanych nazw. Wynik pokazujemy użytkownikowi.

## 7. Zostawione wykonawcy

- Układ plików, np. `szlif.py` plus `strona.html`, albo jeden plik.
- Kształt wewnętrznego API między stroną a serwerem.
- Algorytm porównania (np. `difflib` na słowach) i dokładne granice słów.
- Port domyślny i wygląd strony (CSS, kolory, tryb ciemny).
- Dokładny limit długości tekstu.
- Dokładne brzmienie promptów, w granicach z 4.4.
- Uruchamianie Ollamy w przypadkach niewymienionych w 4.7.
- Miejsce pliku konfiguracyjnego użytkownika.

## 8. Zmiany po pierwszym teście (2026-10-16, decyzja użytkownika)

Test na publicznym artykule medycznym (ok. 1000 słów, bez liczb) pokazał trzy rzeczy. Po pierwsze, cały tekst naraz wraca jako streszczenie: 47 bloków zmieniło się w 7. Po drugie, rundy 2 i 3 potrafią zwrócić tekst bez jednej zmiany. Po trzecie, model dopisuje treść: odpowiada na pytanie z tekstu, wstawia fragment własnego polecenia i dodaje radę. Strażnik liczb nie widział żadnej z tych rzeczy. **[ustalone]**:

- **Praca akapit po akapicie** (zastępuje „nie dzielimy automatycznie” z 4.4).
  - Tekst dzielimy na bloki po pustych wierszach.
  - Przepisujemy tylko akapity prozy (co najmniej 12 słów, bez znaczników listy). Nagłówki, listy i krótkie bloki zostają bez zmian.
  - Rundy, strażnik i reguła stopu działają osobno dla każdego akapitu.
  - Strona podaje postęp („Akapit 3 z 31 · runda 1 z 2”) i notatki przy akapitach.
  - Liczby sprawdzamy na całym tekście i zaznaczamy je w kolumnie Przed.
- **Strażnik, nowe ostrzeżenia** (uzupełnienie 4.5):
  - wynik dłuższy niż max(1,4 × słowa, słowa + 6);
  - wynik krótszy niż 0,7 × słowa (dla akapitów od 8 słów);
  - zmieniona liczba akapitów;
  - słowa o samym tekście („rytm”, „zdania”, „tekst”, „przepis…”, „akapit”, „redakc…”), których nie ma w oryginale.
- **Runda, która zwraca tekst bez zmian, kończy serię** bez ostrzeżenia.
- **Instalator** traktuje ostrzeżenie strażnika przy próbie jako informację, a jako awarię tylko brak tekstu.
- **README** opisuje wynik testu i detektorów, a także ostrzega przed publikowaniem tekstów medycznych, prawnych i finansowych bez eksperta.
- **Weryfikacja i automatyzacja** (decyzja użytkownika z 2026-10-16):
  - przycisk „Kopiuj do weryfikacji” kopiuje prompt z parami akapitów PRZED i PO oraz uwagami strażnika;
  - `szlif.py przepisz` z raportem JSON, plikiem promptu i `--sprawdz`; to ostatnie zleca lokalnemu modelowi porównanie, po kilka akapitów naraz;
  - README ma gotowe polecenie dla agentów.
  - Prompt jest prosty, „Akapit N: BEZ ZMIAN” albo lista DODAJE / POMIJA / ZMIENIA. Pomiar: Bielik 11B przy tabeli z sześcioma kategoriami przeoczył dopisane zdanie, a przy tym formacie je znalazł.
- **Polecenie dla modelu zabrania dopisywania i odpowiadania na pytania z tekstu.** Pomiar po 2 przebiegi na tym samym artykule: 1 i 5 zgłoszonych akapitów wobec 5 i 5 wcześniej, czyli średnio lepiej, ale niepewnie.
- **Po recenzji kodu:**
  - akapit kończy się też pojedynczym Enterem (wklejka z Worda czy Google Docs), a wiersz złamany w środku zdania łączy się z następnym;
  - pozycje list, nagłówki Markdown, cytaty i tabele są osobnymi blokami i zostają bez zmian;
  - ostrzeżenie „meta” wymaga co najmniej dwóch słów o pisaniu w jednym zdaniu;
  - liczba przeniesiona między akapitami jest zgłaszana przy akapicie.
