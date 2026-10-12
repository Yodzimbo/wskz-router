# Proof of Concept (PoC) z opartym na AI systemem kategoryzacji i routingu wiadomości

Zadanie ma na celu wyłącznie sprawdzenie Twojej znajomości technologii oraz umiejętności praktycznych w zakresie integracji systemów i rozwiązań AI.

## Cel zadania

Twoim zadaniem jest przygotowanie pełnego Proof of Concept (PoC) aplikacji mikroserwisowej. Aplikacja ma pełnić rolę inteligentnego routera wiadomości: przyjmować zapytania od użytkowników, interpretować ich treść za pomocą lokalnego modelu językowego (LLM) i automatycznie przekierowywać je do odpowiedniego działu.

Głównym założeniem jest wykorzystanie koncepcji **AI Agenta**, który na podstawie analizy tekstu samodzielnie użyje udostępnionego mu narzędzia (tool) do wysłania wiadomości e-mail.

## Wymagania Infrastrukturalne

Rozwiązanie musi być w pełni oparte na kontenerach.

1. **Docker Compose:** Wymagane jest przygotowanie pełnego pliku konfiguracji `docker-compose.yml`.
2. **Gotowość do pracy:** Po sklonowaniu repozytorium i wykonaniu komendy `docker compose up -d`.

całe środowisko musi poprawnie się uruchomić, zainicjować niezbędne usługi (w tym pobrać ewentualne wagi modelu) i być natychmiast gotowe do przyjmowania requestów.

**Wymagane kontenery w ramach środowiska:**

* **Serwis API:** Napisany w języku PHP lub Python (oparty na oficjalnych obrazach: `php` lub `python`).
* **Narzędzie do testowania e-maili:** Serwer przechwytujący maile. Może to być MailHog (obraz: `mailhog/mailhog`) lub dowolne inne podobne narzędzie.
* **Silnik LLM:** **Ollama** uruchomiona lokalnie w kontenerze. Pozostawiamy dowolność w kwestii tego, czy kontener będzie wykorzystywał CPU, czy wsparcie GPU (obrazy: `ollama/ollama`, `alpine/ollama`).

## Logika Aplikacji i Działanie Agenta

API musi udostępniać endpoint przyjmujący zapytania HTTP. Endpoint powinien przyjmować co najmniej dwa parametry (na przykład w formacie JSON):

* `email`: adres e-mail nadawcy (na przykład `jan.nowak@example.com`),
* `message`: niestandaryzowaną, niedeterministyczną wiadomość tekstową (na przykład *"Nie działa mi komputer"*, *"Chciałbym zgłosić urlop na jutro"*).

Otrzymane dane trafiają do Agenta AI, podłączonego do lokalnie uruchomionej instancji Ollama. Agent ma za zadanie zinterpretować treść wiadomości i zdecydować, pod jaki adres e-mail powinna zostać przekazana sprawa.

Dostępna lista adresów docelowych:

* `human-resources@example.com`
* `help-desk@example.com`
* `it@example.com`
* `kadry@example.com`
* `other@example.com` (jako fallback dla nierozpoznanych zgłoszeń).

Agent **musi** być wyposażony w dedykowane narzędzie (tool) umożliwiające mu wysyłanie wiadomości e-mail. Wysyłka emaili ma być realizowana przez Agenta poprzez wywołanie `tool/function calling`. Wiadomość e-mail ma zostać przechwycona przez kontener z narzędziem testowym e-maili. Wysyłana wiadomość musi mieć ustawiony nagłówek `Reply-To` na adres e-mail nadawcy z pierwotnego requestu.

Dodatkowo wymagane jest wystawienie dokumentacji interfejsu (Swagger/OpenAPI), która musi być dostępna pod adresem `/api/v1/docs`.

## Dokumentacja Projektu

Wymagane jest dołączenie pliku `README.md` w głównym katalogu projektu. Dokumentacja powinna zawierać jasną instrukcję uruchomienia środowiska, krótki opis podjętych decyzji architektonicznych oraz przykładowe zapytanie (cURL lub podobne) pozwalające na szybkie przetestowanie endpointu.

## Sugestie Technologiczne (Opcjonalne)

Do implementacji logiki Agenta w API możesz wykorzystać dedykowane biblioteki ułatwiające budowanie rozwiązań AI i obsługę "function calling". Rekomendujemy:

* **Dla języka Python** należy rozważyć paczki `pydantic-ai` i `langchain`
* **Dla języka PHP** należy rozważyć paczki `neuron-core/neuron-ai`, `symfony/ai-bundle` i `laravel/ai`

## Kryteria Akceptacji (DoD)

* Uruchomienie `docker compose up -d` podnosi w pełni działające API, narzędzie do testowania e-maili oraz Ollamę.
* API udostępnia dokumentację Swagger pod adresem `/api/v1/docs`.
* W repozytorium znajduje się plik `README.md` z instrukcją uruchomienia i opisem projektu.
* Wysłanie requestu na endpoint API skutkuje analizą treści i pojawieniem się nowej wiadomości w panelu webowym narzędzia pocztowego.
* Przechwycona wiadomość jest zaadresowana do prawidłowego działu (zgodnie z listą).
* Przechwycona wiadomość zawiera prawidłowo ustawiony nagłówek `Reply-To`.

---

### Przydatne linki referencyjne:

* [Dokumentacja Docker Compose](https://docs.docker.com/compose/)
* [Obraz Python](https://hub.docker.com/_/python) / [Obraz PHP](https://hub.docker.com/_/php)
* [Przykładowy obraz MailHog](https://hub.docker.com/r/mailhog/mailhog/)
* [Obrazy Ollama](https://hub.docker.com/r/ollama/ollama)
* [Pydantic AI (Python)](https://pypi.org/project/pydantic-ai/)
* [LangChain (Python)](https://pypi.org/project/langchain/)
* [Neuron AI (PHP)](https://packagist.org/packages/neuron-core/neuron-ai)
* [Symfony AI (PHP)](https://packagist.org/packages/symfony/ai-bundle)
* [Laravel AI (PHP)](https://packagist.org/packages/laravel/ai)
