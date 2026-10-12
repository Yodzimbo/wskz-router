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
| `help-desk@example.com` | pomoc użytkownikowi: komputer, sprzęt, konto, hasło |
| `it@example.com` | systemy, serwery, uprawnienia, wdrożenia, oprogramowanie |
| `other@example.com` | wszystko inne albo gdy model nie jest pewien (fallback) |

Lista działów i ich opisy są zdefiniowane raz, w `app/departments.py`; instrukcje agenta i schemat toola są z niej składane.

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
_Do uzupełnienia (M4, M5)._

## Ograniczenia
- Inferencja na CPU: w `dod_check` (i7-11850H, 7 wiadomości) odpowiedź trwała 3,7–16,4 s, mediana 5,3 s. Najdłużej trwała próba prompt injection, bo model najpierw odmówił tekstem i wywołał tool dopiero po przypomnieniu. Na słabszym laptopie czasy będą dłuższe.
- Ollama przetwarza requesty po kolei, więc kilka równoległych zapytań czeka na siebie i może przekroczyć `AGENT_TIMEOUT_S` (504).
- Odpowiedź jest synchroniczna (200 po wysyłce), bez kolejki. Timeout przypadający dokładnie w trakcie wysyłki SMTP nie cofnie już wysłanego maila (ADR-005).

## Treść zadania
[docs/zadanie.md](docs/zadanie.md)

## Licencja
Wszelkie prawa zastrzeżone. Kod udostępniony wyłącznie do oceny w procesie rekrutacyjnym WSKZ, szczegóły w [LICENSE](LICENSE).
