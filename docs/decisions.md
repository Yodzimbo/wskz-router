# Decyzje projektowe (ADR w skrócie)

Każda decyzja: kontekst, decyzja, konsekwencje. Uzupełniane w kolejnych milestone'ach.

## ADR-001: Język promptu i opisów toola
- Kontekst: _do uzupełnienia_
- Decyzja: _do uzupełnienia_
- Konsekwencje: _do uzupełnienia_

## ADR-002: Wybór modelu LLM
- Kontekst: _do uzupełnienia (M2)_
- Decyzja: _do uzupełnienia_
- Konsekwencje: _do uzupełnienia_

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
