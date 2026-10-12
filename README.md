# wskz-router - AI router wiadomości

Proof of concept (zadanie rekrutacyjne WSKZ). API przyjmuje wiadomość od użytkownika, agent LLM (Ollama, lokalnie) analizuje jej treść i sam, przez tool / function calling, wysyła e-mail do właściwego działu z nagłówkiem `Reply-To` ustawionym na adres nadawcy.

## Szybki start
Wymagania: Docker z Docker Compose v2 (`docker compose`; stary `docker-compose` v1 nie był testowany), ok. 8 GB RAM i 12 GB wolnego miejsca na dysku. Wystarczy CPU, GPU nie jest potrzebne. Wolne muszą być porty 8000, 8025 i 1025.

```bash
git clone <adres-repo> wskz-router && cd wskz-router
docker compose up -d
docker compose ps        # api, mailpit, ollama: healthy; ollama-init: Exited (0)
```

Pierwszy start pobiera ok. 6,5 GB: obraz Ollamy oraz wagi modelu `qwen3:4b-instruct` (2,5 GB). Komenda wraca dopiero po pobraniu modelu, a w kilka sekund później API zgłasza gotowość. Czas pierwszego startu zależy głównie od łącza. Zmierzone na świeżym klonie (i7-11850H, szybkie łącze, ok. 70 MB/s): pobranie modelu do pustego wolumenu i start całości to **39 s**, a API zgłasza gotowość 2 s później. W tym pomiarze obraz Ollamy (ok. 4 GB) był już w cache Dockera; wcześniejszy pomiar z pobraniem obrazu (z mniejszym modelem `qwen2.5:3b`) dał 4,5 min. Przy 100 Mb/s samo pobranie 6,5 GB to ok. 9–11 min. Postęp: `docker compose logs -f ollama-init`.

Kolejne starty trwają ok. 10–15 s do gotowości API, bo model zostaje w wolumenie `ollama-models` i nie jest pobierany ponownie. `docker compose down` zatrzymuje środowisko. `docker compose down -v` dodatkowo kasuje wolumen z wagami, więc następny start znów pobierze model.

Domyślnie wszystko działa na CPU. Opcjonalny GPU (NVIDIA) opisuje sekcja [GPU](#gpu-opcjonalnie).

| Usługa | Adres |
|---|---|
| Swagger (dokumentacja API) | http://localhost:8000/api/v1/docs |
| OpenAPI JSON | http://localhost:8000/api/v1/openapi.json |
| Stan zależności | http://localhost:8000/health (200 albo 503 ze szczegółami) |
| Mailpit, panel z przechwyconymi mailami | http://localhost:8025 |

Strona Swaggera ładuje swoje skrypty z CDN, więc przeglądarka potrzebuje dostępu do internetu. Sam `openapi.json` działa offline.

## Przykładowe zapytanie (cURL)
Po `docker compose up -d` (API zgłasza `healthy`):

```bash
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}'
```

Odpowiedź przychodzi po wysłaniu maila (na CPU laptopa zwykle 4–10 s):

```json
{"recipient":"help-desk@example.com","reply_to":"jan.nowak@example.com","subject":"Problem z komputerem","fallback_used":false,"duration_ms":8935}
```

Mail jest widoczny w Mailpicie: http://localhost:8025 (adresat `help-desk@example.com`, nagłówek `Reply-To: jan.nowak@example.com`, w treści streszczenie od modelu i oryginalna wiadomość).

Inne wiadomości do wklejenia w pole `message` (odpowiedzi zmierzone na działającym środowisku, CPU i7-11850H; ostatnie dwie nie występują w ewaluacji ani w instrukcjach agenta):

| `message` | `recipient` | `subject` od modelu | Czas |
|---|---|---|---|
| `Chciałbym zgłosić urlop na jutro` (przykład z zadania) | `kadry@example.com` | Zgłoszenie urlopu na jutro | 6,6 s |
| `Od rana cały dział sprzedaży nie może połączyć się przez VPN z serwerem plików` | `it@example.com` | Problem z połączeniem przez VPN dla działu sprzedaży | 7,6 s |
| `Chciałabym zapisać się na szkolenie z zaawansowanego Excela, czy firma organizuje takie kursy?` | `human-resources@example.com` | Zapisanie się na szkolenie z zaawansowanego Excela | 9,6 s |

Pierwsze zapytanie po starcie bywa wolniejsze (powyższy przykład z komputerem: 14,5 s), bo Ollama ładuje model do pamięci.

Na Windows w PowerShell `curl` to alias `Invoke-WebRequest`, a cytowanie JSON w `curl.exe` jest kłopotliwe. Prościej przez `Invoke-RestMethod`, z treścią wysłaną jako UTF-8 (inaczej Windows PowerShell 5.1 zepsuje polskie znaki):

```powershell
$body = @{ email = "jan.nowak@example.com"; message = "Nie działa mi komputer" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/messages `
  -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($body))
```

| Kod | Znaczenie |
|---|---|
| 200 | agent wysłał maila; `recipient` = dział, `fallback_used: true`, gdy wybrał `other@example.com` |
| 422 | błędny `email`, pusta (albo sama spacja) lub dłuższa niż 5000 znaków `message`; nic nie jest wysyłane |
| 502 | nic nie wysłano: model nie wywołał toola mimo ponowień (`agent_no_tool_call`) albo serwer SMTP niedostępny (`mail_delivery_failed`) |
| 503 | nic nie wysłano: Ollama niedostępna albo zwróciła błąd (`model_unavailable`); można ponowić później |
| 504 | agent nie skończył w `AGENT_TIMEOUT_S` (domyślnie 60 s, `agent_timeout`) |

Błędy 502 / 503 / 504 mają body `{"error": "<kod>", "detail": "..."}`. Każda odpowiedź ma nagłówek `X-Request-ID` (opis w sekcji [Obserwowalność](#obserwowalność)).

## Konfiguracja
Konfiguracja jest opcjonalna. Domyślne wartości są w `docker-compose.yml`, a do nadpisania służy `cp .env.example .env`, np. przy zmianie modelu (`OLLAMA_MODEL`).

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `OLLAMA_MODEL` | `qwen3:4b-instruct` | model pobierany przez `ollama-init` i używany przez agenta |
| `MAIL_FROM` | `router@example.com` | nadawca (`From`) wysyłanych maili |
| `AGENT_TIMEOUT_S` | `60` | limit całego runu agenta (wszystkie requesty do modelu i wysyłka), potem 504 |
| `AGENT_RETRIES` | `3` | ponowienia, gdy model odpowie tekstem albo poda błędne argumenty toola |

Pozostałe limity czasu to ustawienia z domyślną wartością w `app/config.py` (`SMTP_TIMEOUT_S`, `HEALTH_TIMEOUT_S`); compose ich nie przekazuje. Łańcuch timeoutów jest ułożony tak, żeby krótszy limit zawsze zadziałał przed dłuższym i klient dostał konkretny błąd, a nie zerwane połączenie:

| Limit | Wartość | Skutek |
|---|---|---|
| połączenie z Ollamą (klient pydantic-ai) | 5 s, 2 ponowienia z backoffem | zatrzymana Ollama → szybkie 503 `model_unavailable`, bez czekania na `AGENT_TIMEOUT_S` (host, który nie odpowiada wcale, to do ok. 3 × 5 s) |
| `SMTP_TIMEOUT_S` | 10 s | 502 `mail_delivery_failed` |
| `AGENT_TIMEOUT_S` | 60 s (ponad 2 × p95 z ADR-002) | 504 `agent_timeout` |
| `HEALTH_TIMEOUT_S` | 2 s na każdą zależność | `/health` 503 zamiast wiszenia |
| healthcheck `api` w compose | 4 s (request) / 5 s (Docker) | dłuższy niż `/health`, więc nie ucina jego odpowiedzi |

### GPU (opcjonalnie)
Domyślny `docker compose up -d` używa CPU i działa na każdym laptopie. Z kartą NVIDIA można przyspieszyć inferencję plikiem nakładkowym `docker-compose.gpu.yml` (rezerwuje wszystkie GPU dla kontenera `ollama`):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d    # albo: make up-gpu
```

Wymaga sterownika NVIDIA i [nvidia-container-toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) na hoście (w Docker Desktop na Windows: backend WSL2). Bez toolkitu kontener `ollama` nie wystartuje (błąd sterownika urządzenia); wtedy wystarczy zwykły `docker compose up -d`. Wariant GPU nie był testowany na maszynie deweloperskiej (brak toolkitu); AMD / ROCm nie jest obsługiwany.

### Makefile
`make` to tylko skrót: każdy cel uruchamia jedną komendę opisaną w tym README, więc bez `make` (np. na Windows) wystarczy wpisać ją ręcznie. `make` bez argumentów wypisuje cele:

| Cel | Komenda |
|---|---|
| `make up` / `make up-gpu` / `make down` | `docker compose up -d` / z `docker-compose.gpu.yml` / `docker compose down` |
| `make logs` / `make ps` | `docker compose logs -f api` / `docker compose ps` |
| `make test` / `make test-int` | testy unit / integracyjne (sekcja [Testy](#testy-i-ewaluacja)) |
| `make eval` | `.venv/bin/python eval/run_eval.py` |
| `make lint` / `make fmt` | ruff check + format check + mypy / formatowanie ruff |
| `make clean-check CONFIRM=yes` | zimny start: `docker compose down -v` i `up -d`; kasuje pobrany model, bez `CONFIRM=yes` kończy się błędem i nic nie usuwa |

## Architektura
```
POST /api/v1/messages {email, message}
  -> FastAPI: walidacja (pydantic, EmailStr)
  -> agent pydantic-ai (Ollama, qwen3:4b-instruct, temperature 0)
       instrukcje: lista działów; wiadomość użytkownika tylko jako user prompt
       jedyne wyjście agenta: tool send_email(department, subject, body)
  -> send_email: SMTP do Mailpita, To = dział z enuma, Reply-To = email z requestu
  -> 200 {recipient, reply_to, subject, fallback_used, duration_ms}
```

| Dział | Kiedy (opis widziany przez model) |
|---|---|
| `kadry@example.com` | formalności: urlopy, umowy, wynagrodzenia, zaświadczenia |
| `human-resources@example.com` | rekrutacja, rozwój, szkolenia, relacje w zespole |
| `help-desk@example.com` | pierwsza linia pomocy dla jednego pracownika: jego komputer, laptop, peryferia, logowanie, hasło, poczta, oprogramowanie na jego urządzeniu |
| `it@example.com` | systemy i infrastruktura firmy: serwery, sieci, bazy danych, wdrożenia, uprawnienia, licencje, oprogramowanie dla całej firmy |
| `other@example.com` | wszystko, co nie pasuje do powyższych (np. sprawy biura, budynku, administracji), albo gdy model nie jest pewien (fallback) |

Lista działów i ich opisy są zdefiniowane raz, w `app/departments.py`: instrukcje agenta są składane z opisów, a schemat toola bierze z niej enum adresów. Opisy help-desk, IT i other zostały doprecyzowane na podstawie pomyłek w ewaluacji (niżej).

| Plik | Rola |
|---|---|
| `app/main.py` | aplikacja FastAPI, middleware `X-Request-ID` |
| `app/api/messages.py` | endpoint, mapowanie błędów na 502 / 503 / 504, linia logu decyzji |
| `app/logging.py` | formatter logów JSON |
| `app/agent/router_agent.py` | agent, instrukcje, limit ponowień i timeout |
| `app/agent/tools.py` | tool `send_email`: jedyne miejsce, które zleca wysyłkę |
| `app/mail/sender.py` | `EmailMessage` + SMTP (jedyny kod SMTP) |
| `app/departments.py` | enum 5 adresów + opisy działów |

## Obserwowalność
Każdy request, który przeszedł walidację, zostawia w logach API dokładnie jedną linię JSON z decyzją, także przy błędzie (wtedy `outcome` to kod błędu, a pola decyzji są `null`):

```bash
docker compose logs api | grep '"logger": "app.api.messages"'   # albo: grep <X-Request-ID>
```

```json
{"ts": "2026-10-12T10:15:02.481+00:00", "level": "INFO", "logger": "app.api.messages", "msg": "routed", "request_id": "3f2a9c0e8b7d4e1fa6c5b4d3e2f1a0b9", "outcome": "sent", "status": 200, "recipient": "help-desk@example.com", "fallback_used": false, "model_requests": 1, "duration_ms": 5321, "smtp_ms": 4, "message_length": 22, "sender_domain": "example.com"}
```

Log nigdy nie zawiera treści wiadomości ani pełnego adresu nadawcy, tylko długość wiadomości i domenę. `model_requests` > 1 oznacza, że model potrzebował przypomnienia (ponowienia), a `fallback_used: true` to wybór `other@example.com`.

`X-Request-ID` łączy odpowiedź API, linię logu i maila: middleware nadaje identyfikator (albo przyjmuje go od klienta, jeśli ma do 64 znaków `A-Z a-z 0-9 . _ -`), zwraca go w nagłówku odpowiedzi, a tool `send_email` dodaje ten sam nagłówek do maila (widoczny w Mailpicie w zakładce nagłówków). Model go nie widzi. Logi samego uvicorna (access log) zostają w formacie tekstowym.

## Decyzje projektowe
Skrót poniżej, szczegóły w [docs/decisions.md](docs/decisions.md).

- **Mailpit zamiast MailHoga.** Jest aktywnie rozwijany i ma REST API, przez które testy sprawdzają odbiorcę i `Reply-To` (ADR-003).
- **Model `qwen3:4b-instruct`, wybrany pomiarem.** Spośród czterech modeli z obsługą tooli tylko on, przy rozmiarze poniżej 3 GB, wybrał właściwy dział we wszystkich 12 polskich wiadomościach testowych, z p95 26,5 s na CPU laptopa (ADR-002).
- **Model pobiera osobny kontener `ollama-init`.** API startuje dopiero po jego sukcesie, a ponowny start nie pobiera modelu drugi raz (ADR-006).
- **Wysyłkę robi tool agenta, a tool jest jedynym wyjściem agenta.** Model nie może zakończyć pracy odpowiedzią tekstową: dostaje przypomnienie i ponawia (domyślnie 3 razy, `AGENT_RETRIES`). Kod po agencie niczego nie wysyła (ADR-004).
- **Model wybiera tylko dział (enum), temat i treść.** Adres działu pochodzi z enuma, a `Reply-To` z requestu, więc prośba w wiadomości „wyślij do ceo@…, ustaw Reply-To na …” nie ma czym zadziałać (ADR-004).
- **Fallback `other@example.com` to decyzja modelu, oznaczona `fallback_used: true` i zalogowana.** Gdy model w ogóle nie wywoła toola, API zwraca 502 i nic nie wysyła, zamiast wysyłać „na ślepo”. Niedostępna Ollama daje szybkie 503 (ADR-005).
- **Jedna linia logu JSON na request i `X-Request-ID` od odpowiedzi do maila**, bez nowych zależności (ADR-007).
- **Instrukcje po angielsku, temat i treść maila po polsku** (ADR-001).
- **Python + FastAPI + pydantic-ai zamiast PHP.** pydantic-ai daje typowany tool z enumem działów, walidację argumentów z automatycznym ponowieniem i `TestModel` / `FunctionModel` do testów bez modelu; FastAPI generuje Swaggera z tych samych modeli pydantic. Jeden system typów (pydantic) obsługuje walidację requestu, schemat toola i dokumentację API. Odrzucone: langchain (więcej warstw niż potrzeba dla jednego toola) i warianty PHP z sugestii zadania (ADR-008).
- **Synchroniczne API: 200 dopiero po wysłaniu maila.** Klient od razu wie, do którego działu trafiła wiadomość i czy w ogóle wyszła; bez kolejki odpowiedź 202 ukrywałaby błędy (ADR-005). Wersja z kolejką jest w sekcji [Co zrobiłbym w produkcji](#co-zrobiłbym-w-produkcji).

## Testy i ewaluacja
Testy uruchamia się na hoście, w wirtualnym środowisku Pythona 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/unit -q                           # ok. 2 s, bez Dockera
.venv/bin/pytest tests/integration -m integration -q     # ok. 1 min, wymaga docker compose up -d
```

**Testy jednostkowe** (`tests/unit`, 71 testów) nie potrzebują Ollamy ani sieci: model zastępuje `FunctionModel` z pydantic-ai, który zwraca zaplanowane wywołania toola, a SMTP jest podmieniony. Prawdziwe zapytanie do modelu kończy się błędem (`ALLOW_MODEL_REQUESTS = False`). Sprawdzają kontrakt agenta:
- mail wysyła wyłącznie tool `send_email` (sprawdzane też statycznie: `smtplib` tylko w `app/mail/`, funkcja wysyłająca importowana tylko przez tool), a gdy model odpowie tekstem zamiast toola, nic nie zostaje wysłane i API zwraca 502;
- model widzi w toolu tylko dział (enum 5 adresów), temat i treść. Adres spoza listy albo dodatkowy argument `reply_to` jest odrzucany z prośbą o poprawkę, a `Reply-To` zawsze pochodzi z requestu;
- treść wiadomości trafia do modelu tylko jako wiadomość użytkownika, nigdy do instrukcji systemowych;
- lista działów w kodzie, prompcie i tabeli w tym README jest ta sama, fallback `other@` jest oznaczony w odpowiedzi i zalogowany;
- walidacja requestu (422), mapowanie błędów (502, 503, 504), timeout, `/health`, sanityzacja tematu maila;
- linia logu decyzji (pola, brak treści wiadomości i lokalnej części adresu, `fallback_used`) oraz `X-Request-ID` w odpowiedzi, logu i mailu (także odrzucenie niebezpiecznego identyfikatora od klienta).

**Testy integracyjne** (`tests/integration`, 6 testów) wysyłają requesty do działającego API i sprawdzają maile przez API Mailpit: dokładnie jeden mail na request, adresat zgodny z odpowiedzią API i z listy działów, nagłówek `Reply-To` równy nadawcy, niepusty temat. Dział sprawdzają tylko dla dwóch przykładów z zadania (komputer → `help-desk@`, urlop → `kadry@`). Trafność na trudniejszych wiadomościach mierzy ewaluacja. Dodatkowo: próba prompt injection nie wysyła maila do `ceo@` ani z `Reply-To` napastnika, a pusta wiadomość daje 422 bez maila. Każdy test używa własnego adresu nadawcy i szuka swojego maila po `Reply-To`, więc testy nie czyszczą skrzynki Mailpit. Gdy compose nie działa, testy są pomijane (skip) z podpowiedzią `docker compose up -d`. Czas na CPU (i7-11850H): 52 s.

### Ewaluacja
Ewaluacja mierzy, jak często model wybiera właściwy dział. To nie jest test pass/fail: wynik zależy od modelu, nie tylko od kodu. Skrypt `eval/run_eval.py` wysyła 24 polskie wiadomości z `eval/cases.jsonl` do działającego API, a każdy mail znajduje w Mailpicie po unikalnym `Reply-To` i sprawdza go tak jak testy integracyjne. Wynik (JSON z każdą odpowiedzią) trafia do `eval/results/`.

```bash
docker compose up -d
.venv/bin/python eval/run_eval.py                  # ok. 3 min na CPU (i7-11850H)
.venv/bin/python eval/run_eval.py --repeat 2 --label final
```

Przypadki: 12 jednoznacznych (po 3 na kadry, HR, help-desk, IT, w tym oba przykłady z zadania), 6 granicznych (kadry/HR, help-desk/IT, IT/inne, HR/inne), 2 próby prompt injection i 4 sprawy „inne”, pisane różnie: formalnie, potocznie, z literówkami, bez polskich znaków, wielowątkowo. Poza dwoma przykładami z zadania nie powtarzają wiadomości z pomiaru wyboru modelu (ADR-002) ani z instrukcji agenta, co sprawdza test `tests/unit/test_eval_cases.py`.

Wyniki z 2026-10-12, `qwen3:4b-instruct`, Ollama na CPU (i7-11850H):

| Metryka | Przed strojeniem | Po strojeniu (2 powtórzenia) |
|---|---|---|
| Trafność ogólna | 70,8% (17/24) | 95,8% (46/48) |
| Jednoznaczne | 91,7% (11/12) | 100% (24/24) |
| Graniczne | 50,0% (3/6) | 83,3% (10/12) |
| Prompt injection | 2/2 | 4/4 |
| Inne | 25,0% (1/4) | 100% (8/8) |
| Recall: kadry / HR / help-desk / IT / other | 100 / 100 / 50 / 75 / 25% | 100 / 100 / 83 / 100 / 100% |
| Fallback (`fallback_used: true`) | 4,2% | 16,7% |
| Mail zgodny z API (1 mail, `To` = `recipient`, `Reply-To` = nadawca) | 24/24 | 48/48 |
| Błędy HTTP (502 / 504) | 0 | 0 |
| Czas odpowiedzi: mediana / p95 | 7,1 s / 8,2 s | 7,0 s / 8,3 s |

Przed strojeniem model kierował do IT awarie sprzętu i problemy z oprogramowaniem pojedynczego pracownika, a sprawy biurowe (zepsuty ekspres, rezerwacja sali, przeciek z sufitu) do help-desku albo HR, bo opis `other@` nie mówił, co do niego należy. Obie przyczyny to niejasne definicje działów, więc poprawione zostały tylko opisy w `app/departments.py`: help-desk to pomoc dla jednego pracownika i jego urządzenia, IT to systemy i infrastruktura firmy, a `other@` obejmuje sprawy biura i budynku. Nowe sformułowania (laptop, logowanie, licencje, sprawy biura i budynku) opisują kategorie, w których model się mylił, a nie cytują przypadków, ale wynik po strojeniu jest mierzony na tym samym zestawie, więc jest optymistyczny; niezależną kontrolą są ręczne scenariusze kontrolne na działającym środowisku (wiadomości spoza tego zestawu, w tym próba injection) i przykłady z sekcji [Przykładowe zapytanie](#przykładowe-zapytanie-curl). Jedyna pozostała pomyłka, prośba o instalację Pythona i Dockera bez uprawnień administratora (oczekiwany help-desk, model wybiera IT), jest naprawdę dwuznaczna, bo dotyczy zarówno komputera pracownika, jak i uprawnień. Oczekiwania dla przypadków granicznych: zmiana wymiaru etatu → kadry (zmiana umowy), niespełniona obietnica podwyżki → HR (rozwój i relacja z przełożonym, nie naliczanie płac), logowanie do CRM i instalacja programów na własnym laptopie → help-desk (problem jednego pracownika), licencja dla działu → IT, wyjazd integracyjny → HR (relacje w zespole). Przy `temperature=0` oba powtórzenia dały te same decyzje, a obie próby injection trafiły do działu z listy z `Reply-To` nadawcy.

## Ograniczenia
- Inferencja na CPU: w ręcznych scenariuszach kontrolnych (i7-11850H, 7 wiadomości spoza zestawu ewaluacji) odpowiedź trwała 3,7–16,4 s, mediana 5,3 s. Najdłużej trwała próba prompt injection, bo model najpierw odmówił tekstem i wywołał tool dopiero po przypomnieniu. Na słabszym laptopie czasy będą dłuższe.
- Ollama przetwarza requesty po kolei, więc kilka równoległych zapytań czeka na siebie i może przekroczyć `AGENT_TIMEOUT_S` (504).
- Odpowiedź jest synchroniczna (200 po wysyłce), bez kolejki. Timeout przypadający dokładnie w trakcie wysyłki SMTP nie cofnie już wysłanego maila (ADR-005).
- Brak trwałej kolejki i ponowień wysyłki: gdy SMTP jest niedostępny, API zwraca 502 i wiadomość trzeba wysłać jeszcze raz.
- Brak uwierzytelniania i limitu requestów: każdy, kto ma dostęp do portu 8000, może wysyłać maile do działów (w PoC tylko do Mailpita). Panel Mailpita (8025) też nasłuchuje na wszystkich interfejsach, więc przechwycone maile z treścią wiadomości widzi każdy w tej samej sieci.
- Nieprzewidziany wyjątek kończy się odpowiedzią 500 bez nagłówka `X-Request-ID` i bez linii decyzji w logu. Endpoint mapuje wszystkie znane błędy (502 / 503 / 504), a globalny handler to rzecz na produkcję (ADR-007).
- Ewaluacja i testy integracyjne sprawdzają skrzynkę Mailpita w uproszczony sposób. Przy odpowiedzi innej niż 200 ewaluacja zagląda do skrzynki tylko raz, od razu, więc nie wykryłaby maila wysłanego z opóźnieniem (np. 504 w trakcie wysyłki SMTP). Test injection szuka maila do `ceo@` tylko na pierwszej stronie listy Mailpita. To drugie wystarcza, bo Mailpit zwraca najpierw najnowsze maile.
- Mały model (4B) myli się w sprawach na granicy dwóch działów: 83% trafności na przypadkach granicznych w ewaluacji, a wynik po strojeniu jest optymistyczny (sekcja [Ewaluacja](#ewaluacja)).

## Co zrobiłbym w produkcji
- **Kolejka i worker:** API zapisuje zgłoszenie i od razu zwraca 202 z identyfikatorem i adresem do sprawdzenia statusu, a worker uruchamia agenta. Idempotencja po `X-Request-ID`, żeby ponowiony request nie wysłał drugiego maila.
- **Niezawodna wysyłka:** ponowienia SMTP z backoffem, kolejka błędów (DLQ) z alertem zamiast 502 dla klienta.
- **Jakość routingu:** informacja zwrotna od działów („to nie do nas”) jako nowe przypadki ewaluacji, ewaluacja w CI przy każdej zmianie promptu, opisów działów albo modelu, z progiem trafności blokującym wdrożenie. Wersjonowanie promptu i modelu, zapisywane w logu decyzji.
- **Obserwowalność:** metryki (czas, trafność fallbacku, liczba ponowień, błędy 5xx), tracing requestu przez agenta i SMTP, logi uvicorna w JSON, globalny handler 500 z `X-Request-ID`.
- **Bezpieczeństwo:** uwierzytelnianie klientów API i limit requestów na klienta.
- **Dane osobowe:** zasady retencji maili i logów, maskowanie danych w treści przed zapisem tam, gdzie treść nie jest potrzebna.
- **Wydajność:** GPU albo większy model za flagą konfiguracji, wybierany tym samym pomiarem co w ADR-002.

## Treść zadania
[docs/zadanie.md](docs/zadanie.md)

## Licencja
Wszelkie prawa zastrzeżone. Kod udostępniony wyłącznie do oceny w procesie rekrutacyjnym WSKZ, szczegóły w [LICENSE](LICENSE).
