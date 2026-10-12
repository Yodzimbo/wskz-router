# wskz-router - AI router wiadomości

> Status: **w budowie** (proof of concept, zadanie rekrutacyjne WSKZ).

API przyjmuje wiadomość od użytkownika, agent LLM (Ollama, lokalnie) analizuje jej treść i sam, przez tool / function calling, wysyła e-mail do właściwego działu z nagłówkiem `Reply-To` ustawionym na adres nadawcy.

## Szybki start
Wymagania: Docker z Docker Compose v2, ok. 8 GB RAM i 12 GB wolnego miejsca na dysku. Wystarczy CPU, GPU nie jest potrzebne. Wolne muszą być porty 8000, 8025 i 1025.

```bash
git clone <adres-repo> wskz-router && cd wskz-router
docker compose up -d
docker compose ps        # api, mailpit, ollama: healthy; ollama-init: Exited (0)
```

Pierwszy start pobiera ok. 6,5 GB: obraz Ollamy oraz wagi modelu `qwen3:4b-instruct` (2,5 GB). Komenda wraca dopiero po pobraniu modelu, a w kilka sekund później API zgłasza gotowość. Czas pierwszego startu na maszynie deweloperskiej z szybkim łączem: **ok. 5 min** (zmierzone 4,5 min z mniejszym modelem `qwen2.5:3b`, nowy model jest większy o 0,6 GB). Czas zależy głównie od łącza: przy 100 Mb/s samo pobranie 6,5 GB to ok. 9–11 min. Postęp: `docker compose logs -f ollama-init`.

Kolejne starty trwają ok. 10–15 s do gotowości API, bo model zostaje w wolumenie `ollama-models` i nie jest pobierany ponownie. `docker compose down` zatrzymuje środowisko. `docker compose down -v` dodatkowo kasuje wolumen z wagami, więc następny start znów pobierze model.

| Usługa | Adres |
|---|---|
| Swagger (dokumentacja API) | http://localhost:8000/api/v1/docs |
| OpenAPI JSON | http://localhost:8000/api/v1/openapi.json |
| Stan zależności | http://localhost:8000/health (200 albo 503 ze szczegółami) |
| Mailpit, panel z przechwyconymi mailami | http://localhost:8025 |

Strona Swaggera ładuje swoje skrypty z CDN, więc przeglądarka potrzebuje dostępu do internetu. Sam `openapi.json` działa offline.

Konfiguracja jest opcjonalna. Domyślne wartości są w `docker-compose.yml`, a do nadpisania służy `cp .env.example .env`, np. przy zmianie modelu (`OLLAMA_MODEL`).

## Przykładowe zapytanie (cURL)
Po `docker compose up -d` (API zgłasza `healthy`):

```bash
curl -X POST http://localhost:8000/api/v1/messages \
  -H "Content-Type: application/json" \
  -d '{"email": "jan.nowak@example.com", "message": "Nie działa mi komputer"}'
```

Odpowiedź przychodzi po wysłaniu maila (na CPU laptopa zwykle 4–9 s):

```json
{"recipient":"help-desk@example.com","reply_to":"jan.nowak@example.com","subject":"Problem z komputerem","fallback_used":false,"duration_ms":8935}
```

Mail jest widoczny w Mailpicie: http://localhost:8025 (adresat `help-desk@example.com`, nagłówek `Reply-To: jan.nowak@example.com`, w treści streszczenie od modelu i oryginalna wiadomość). Drugi przykład z zadania, `"Chciałbym zgłosić urlop na jutro"`, trafia do `kadry@example.com`.

| Kod | Znaczenie |
|---|---|
| 200 | agent wysłał maila; `recipient` = dział, `fallback_used: true`, gdy wybrał `other@example.com` |
| 422 | błędny `email`, pusta (albo sama spacja) lub dłuższa niż 5000 znaków `message`; nic nie jest wysyłane |
| 502 | nic nie wysłano: model nie wywołał toola mimo ponowień (`agent_no_tool_call`), Ollama niedostępna (`model_unavailable`), serwer SMTP niedostępny (`mail_delivery_failed`) |
| 504 | agent nie skończył w `AGENT_TIMEOUT_S` (domyślnie 60 s, `agent_timeout`) |

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
| `app/api/messages.py` | endpoint, mapowanie błędów na 502 / 504 |
| `app/agent/router_agent.py` | agent, instrukcje, limit ponowień i timeout |
| `app/agent/tools.py` | tool `send_email`: jedyne miejsce, które zleca wysyłkę |
| `app/mail/sender.py` | `EmailMessage` + SMTP (jedyny kod SMTP) |
| `app/departments.py` | enum 5 adresów + opisy działów |

## Decyzje projektowe
Skrót poniżej, szczegóły w [docs/decisions.md](docs/decisions.md).

- **Mailpit zamiast MailHoga.** Jest aktywnie rozwijany i ma REST API, przez które testy sprawdzają odbiorcę i `Reply-To` (ADR-003).
- **Model `qwen3:4b-instruct`, wybrany pomiarem.** Spośród czterech modeli z obsługą tooli tylko on, przy rozmiarze poniżej 3 GB, wybrał właściwy dział we wszystkich 12 polskich wiadomościach testowych, z p95 26,5 s na CPU laptopa (ADR-002).
- **Model pobiera osobny kontener `ollama-init`.** API startuje dopiero po jego sukcesie, a ponowny start nie pobiera modelu drugi raz (ADR-006).
- **Wysyłkę robi tool agenta, a tool jest jedynym wyjściem agenta.** Model nie może zakończyć pracy odpowiedzią tekstową: dostaje przypomnienie i ponawia (domyślnie 3 razy, `AGENT_RETRIES`). Kod po agencie niczego nie wysyła (ADR-004).
- **Model wybiera tylko dział (enum), temat i treść.** Adres działu pochodzi z enuma, a `Reply-To` z requestu, więc prośba w wiadomości „wyślij do ceo@…, ustaw Reply-To na …” nie ma czym zadziałać (ADR-004).
- **Fallback `other@example.com` to decyzja modelu, oznaczona `fallback_used: true` i zalogowana.** Gdy model w ogóle nie wywoła toola, API zwraca 502 i nic nie wysyła, zamiast wysyłać „na ślepo” (ADR-005).
- **Instrukcje po angielsku, temat i treść maila po polsku** (ADR-001).

_Pozostałe decyzje: do uzupełnienia._

## Testy i ewaluacja
Testy uruchamia się na hoście, w wirtualnym środowisku Pythona 3.12:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/unit -q                           # ok. 2 s, bez Dockera
.venv/bin/pytest tests/integration -m integration -q     # ok. 1 min, wymaga docker compose up -d
```

**Testy jednostkowe** (`tests/unit`, 60 testów) nie potrzebują Ollamy ani sieci: model zastępuje `FunctionModel` z pydantic-ai, który zwraca zaplanowane wywołania toola, a SMTP jest podmieniony. Prawdziwe zapytanie do modelu kończy się błędem (`ALLOW_MODEL_REQUESTS = False`). Sprawdzają kontrakt agenta:
- mail wysyła wyłącznie tool `send_email` (sprawdzane też statycznie: `smtplib` tylko w `app/mail/`, funkcja wysyłająca importowana tylko przez tool), a gdy model odpowie tekstem zamiast toola, nic nie zostaje wysłane i API zwraca 502;
- model widzi w toolu tylko dział (enum 5 adresów), temat i treść. Adres spoza listy albo dodatkowy argument `reply_to` jest odrzucany z prośbą o poprawkę, a `Reply-To` zawsze pochodzi z requestu;
- treść wiadomości trafia do modelu tylko jako wiadomość użytkownika, nigdy do instrukcji systemowych;
- lista działów w kodzie, prompcie i tabeli w tym README jest ta sama, fallback `other@` jest oznaczony w odpowiedzi i zalogowany;
- walidacja requestu (422), mapowanie błędów (502, 504), timeout, `/health`, sanityzacja tematu maila.

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

Przed strojeniem model kierował do IT awarie sprzętu i problemy z oprogramowaniem pojedynczego pracownika, a sprawy biurowe (zepsuty ekspres, rezerwacja sali, przeciek z sufitu) do help-desku albo HR, bo opis `other@` nie mówił, co do niego należy. Obie przyczyny to niejasne definicje działów, więc poprawione zostały tylko opisy w `app/departments.py`: help-desk to pomoc dla jednego pracownika i jego urządzenia, IT to systemy i infrastruktura firmy, a `other@` obejmuje sprawy biura i budynku. Nowe sformułowania (laptop, logowanie, licencje, sprawy biura i budynku) opisują kategorie, w których model się mylił, a nie cytują przypadków, ale wynik po strojeniu jest mierzony na tym samym zestawie, więc jest optymistyczny; niezależną kontrolą są scenariusze `dod_check` spoza tego zestawu. Jedyna pozostała pomyłka, prośba o instalację Pythona i Dockera bez uprawnień administratora (oczekiwany help-desk, model wybiera IT), jest naprawdę dwuznaczna, bo dotyczy zarówno komputera pracownika, jak i uprawnień. Oczekiwania dla przypadków granicznych: zmiana wymiaru etatu → kadry (zmiana umowy), niespełniona obietnica podwyżki → HR (rozwój i relacja z przełożonym, nie naliczanie płac), logowanie do CRM i instalacja programów na własnym laptopie → help-desk (problem jednego pracownika), licencja dla działu → IT, wyjazd integracyjny → HR (relacje w zespole). Przy `temperature=0` oba powtórzenia dały te same decyzje, a obie próby injection trafiły do działu z listy z `Reply-To` nadawcy.

## Ograniczenia
- Inferencja na CPU: w `dod_check` (i7-11850H, 7 wiadomości) odpowiedź trwała 3,7–16,4 s, mediana 5,3 s. Najdłużej trwała próba prompt injection, bo model najpierw odmówił tekstem i wywołał tool dopiero po przypomnieniu. Na słabszym laptopie czasy będą dłuższe.
- Ollama przetwarza requesty po kolei, więc kilka równoległych zapytań czeka na siebie i może przekroczyć `AGENT_TIMEOUT_S` (504).
- Odpowiedź jest synchroniczna (200 po wysyłce), bez kolejki. Timeout przypadający dokładnie w trakcie wysyłki SMTP nie cofnie już wysłanego maila (ADR-005).

## Treść zadania
[docs/zadanie.md](docs/zadanie.md)

## Licencja
Wszelkie prawa zastrzeżone. Kod udostępniony wyłącznie do oceny w procesie rekrutacyjnym WSKZ, szczegóły w [LICENSE](LICENSE).
