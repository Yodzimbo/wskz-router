# Decyzje projektowe (ADR w skrócie)

Każda decyzja: kontekst, decyzja, konsekwencje. Uzupełniane w kolejnych milestone'ach.

## ADR-001: Język promptu i opisów toola
- Kontekst: _do uzupełnienia_
- Decyzja: _do uzupełnienia_
- Konsekwencje: _do uzupełnienia_

## ADR-002: Wybór modelu LLM
- Kontekst: model ma niezawodnie wywoływać tool `send_email` z poprawnym działem (enum 5 adresów), rozumieć polskie wiadomości i odpowiadać w rozsądnym czasie na CPU przeciętnego laptopa. Wybór na podstawie pomiaru, nie opinii. Kryterium ustalone przed pomiarem: (1) ≥ 90% poprawnych działów i 100% wywołań toola w lepszym wariancie rejestracji toola, (2) p95 ≤ 30 s, (3) najmniejszy rozmiar pobrania. `qwen2.5:7b` tylko jako punkt odniesienia.
- Pomiar (2026-10-12): Ollama 0.40.2, pydantic-ai 2.55.0, i7-11850H (16 wątków), 30 GB RAM, tylko CPU. Agent pydantic-ai w kontenerze `api`, ta sama ścieżka sieciowa co produkcja (`http://ollama:11434/v1`). 12 polskich wiadomości (6 jednoznacznych, w tym oba przykłady z zadania, 4 graniczne kadry/HR i help-desk/IT, 1 próba prompt injection, 1 „inne”), po 3 powtórzenia, `temperature=0`, `retries=2`, rozgrzewka poza statystyką. Dwa warianty toola o tej samej sygnaturze `send_email(department: Department, subject, body)`: **A** zwykły tool (`@agent.tool`) z odpowiedzią tekstową, **B** tool jako jedyne wyjście agenta (`output_type=ToolOutput(send_email)`), w którym odpowiedź tekstem wywołuje automatyczny retry.

  | Model | Pobranie | Wariant | Wywołany tool | Poprawny dział | Przebiegi z retry | Mediana | p95 |
  |---|---|---|---|---|---|---|---|
  | `qwen2.5:3b` | 1,9 GB | A | 91,7% | 83,3% | 0% | 7,1 s | 8,4 s |
  | `qwen2.5:3b` | 1,9 GB | B | 100% | 83,3% | 8,3% | 4,3 s | 17,8 s |
  | **`qwen3:4b-instruct`** | 2,5 GB | A | 91,7% | 91,7% | 0% | 7,8 s | 10,6 s |
  | **`qwen3:4b-instruct`** | 2,5 GB | **B** | **100%** | **100%** | 8,3% | 5,9 s | 26,5 s |
  | `llama3.2:3b` | 2,0 GB | A | 97,2% | 66,7% | 8,3% | 10,9 s | 19,3 s |
  | `llama3.2:3b` | 2,0 GB | B | 100% | 66,7% | 8,3% | 4,2 s | 14,6 s |
  | `qwen2.5:7b` (odniesienie) | 4,7 GB | A | 100% | 91,7% | 0% | 14,7 s | 17,2 s |
  | `qwen2.5:7b` (odniesienie) | 4,7 GB | B | 100% | 91,7% | 0% | 10,3 s | 12,4 s |

  Przy `temperature=0` powtórzenia dają te same decyzje (z jednym wyjątkiem: `llama3.2:3b`, wariant A, injection), więc 36 przebiegów to w praktyce 12 przypadków. Kontekst: maks. 2002 tokenów wejścia, poniżej domyślnych 4096 Ollamy na CPU.
- Decyzja: domyślny model `qwen3:4b-instruct` (Qwen3 4B Instruct 2507, bez trybu „thinking”; w pomiarze 0 części thinking), jako jedyny z małych modeli spełnia warunek (1). Dla agenta w M3 wariant B: każdy run kończy się wywołaniem toola albo jawnym błędem, a nie odpowiedzią tekstem bez wysyłki.
- Obserwacje: w wariancie A modele qwen przy próbie injection odpowiadają tekstem (odmowa) i nie wywołują toola. W wariancie B ten sam przypadek kończy się poprawnym działem po retry, a jest to jedyny przypadek z retry: `qwen3:4b-instruct` dwa razy odmawia tekstem i wywołuje tool dopiero za trzecią próbą. Ten jeden przypadek odpowiada za p95 26,5 s. `qwen2.5:3b` myli urlop (kadry) z HR i przy injection wybiera `other@`. `llama3.2:3b` wybiera kadry dla serwera, dostępów i spraw „innych”, a przy injection wywołuje tool kilka razy. `qwen2.5:7b` ma jeden błąd (sprawa „inna” → HR) i jest 2× większy.
- Odrzucone: `qwen2.5:3b` i `llama3.2:3b` (trafność poniżej 90%), `qwen2.5:7b` jako domyślny (4,7 GB pobrania, mediana 10,3 s wobec 5,9 s i niższa trafność), `qwen3:4b` z trybem thinking (dłuższe odpowiedzi, a wyłączanie thinkingu przez endpoint `/v1` Ollamy jest niepewne).
- Konsekwencje: pierwszy start pobiera o ok. 0,6 GB więcej niż z `qwen2.5:3b`. `retries=2` to minimum: przypadek injection wykorzystał oba retry, więc M3 ustawia limit z zapasem i ma jawny fallback po jego przekroczeniu. Czas odpowiedzi do ok. 30 s na tym CPU, na słabszym laptopie więcej, stąd `AGENT_TIMEOUT_S=60`. 12 przypadków to próba sprawdzająca, nie pełna ewaluacja; pełny eval z ok. 20 przypadkami jest w M5. Skrypt pomiaru, przypadki i surowe wyniki są na branchu `spike/model-selection` (`eval/spike_models.py`, `eval/spike_cases.jsonl`, `eval/spike_results.json`).

## ADR-003: Narzędzie do testowania e-maili
- Kontekst: zadanie wymaga serwera przechwytującego maile; podaje MailHog jako przykład i dopuszcza „dowolne inne podobne narzędzie”. MailHog nie jest rozwijany od kilku lat.
- Decyzja: Mailpit (`axllent/mailpit`, przypięta wersja). Panel webowy i REST API na porcie 8025, SMTP na 1025, bez TLS i bez logowania.
- Konsekwencje: przez REST API (`/api/v1/messages`, `/api/v1/message/{ID}`) testy integracyjne sprawdzają odbiorcę i `Reply-To`, a nie tylko to, że mail doszedł. Obraz ma wbudowane `mailpit readyz`, więc healthcheck nie potrzebuje `curl`.

## ADR-004: Kontrakt toola wysyłającego e-mail
- Kontekst: _do uzupełnienia (M3)_
- Decyzja: _do uzupełnienia_
- Konsekwencje: _do uzupełnienia_

## ADR-005: Fallback przy braku decyzji modelu
- Kontekst: _do uzupełnienia (M3)_
- Decyzja: _do uzupełnienia_
- Konsekwencje: _do uzupełnienia_

## ADR-006: Pobieranie modelu w osobnym kontenerze `ollama-init`
- Kontekst: po `docker compose up -d` środowisko ma być gotowe do pracy, czyli model musi już być pobrany. Pierwsze pobranie to kilka GB.
- Decyzja: jednorazowy kontener `ollama-init` na tym samym oficjalnym obrazie Ollamy uruchamia `ollama show <model> || ollama pull <model>` na serwerze `ollama`. API startuje dopiero po jego sukcesie (`depends_on: service_completed_successfully`) i po zdrowym Mailpicie. Wagi trzyma nazwany wolumen `ollama-models`.
- Odrzucone: pull w entrypoincie kontenera `ollama` (miesza serwer z inicjalizacją, healthcheck musiałby czekać na pull); pull w API przy starcie (API zależne od zewnętrznej sieci, wolny i niepewny start); sam `ollama pull` bez `show` (każdy restart wymagałby dostępu do rejestru modeli).
- Konsekwencje: `up -d` wraca dopiero po pobraniu modelu, a kolejne starty nie pobierają go ponownie i działają bez internetu. `docker compose down -v` kasuje wolumen z wagami. Port Ollamy (11434) nie jest wystawiony na hosta, żeby nie kolidować z lokalnie zainstalowaną Ollamą. `/health` sprawdza listę modeli i powitanie SMTP, nigdy nie uruchamia inferencji.
