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

Pierwszy start pobiera ok. 6 GB: obraz Ollamy oraz wagi modelu `qwen2.5:3b`. Komenda wraca dopiero po pobraniu modelu, a w kilka sekund później API zgłasza gotowość. Zmierzony czas pierwszego startu na maszynie deweloperskiej z szybkim łączem: **ok. 4,5 min**. Czas zależy głównie od łącza: przy 100 Mb/s samo pobranie 6 GB to ok. 8–10 min. Postęp: `docker compose logs -f ollama-init`.

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
_Do uzupełnienia (M3)._

## Architektura
_Do uzupełnienia (M3)._

## Decyzje projektowe
Skrót poniżej, szczegóły w [docs/decisions.md](docs/decisions.md).

- **Mailpit zamiast MailHoga.** Jest aktywnie rozwijany i ma REST API, przez które testy sprawdzają odbiorcę i `Reply-To` (ADR-003).
- **Model pobiera osobny kontener `ollama-init`.** API startuje dopiero po jego sukcesie, a ponowny start nie pobiera modelu drugi raz (ADR-006).

_Pozostałe decyzje: do uzupełnienia._

## Testy i ewaluacja
_Do uzupełnienia (M4, M5)._

## Ograniczenia
_Do uzupełnienia._

## Treść zadania
[docs/zadanie.md](docs/zadanie.md)

## Licencja
Wszelkie prawa zastrzeżone. Kod udostępniony wyłącznie do oceny w procesie rekrutacyjnym WSKZ, szczegóły w [LICENSE](LICENSE).
