# sensitive-guard

Warstwa prywatności na **Laya** — otwartym klasyfikatorze decyzji (jak Jev), z wagami Apache-2.0. Wykrywa dane wrażliwe w tekście, kategoryzuje je i decyduje, czy można je puścić dalej, zredagować, czy zablokować.

Laya nie generuje tekstu. Dostaje stan i zamkniętą listę odpowiedzi, a zwraca skalibrowane prawdopodobieństwa w jednym przebiegu. Dzięki temu warstwa działa lokalnie, bez wysyłania treści do zamkniętego API.

## Co robi

1. **Finder** — te same rodziny regex co w treningu `goku-san/laya-experts` (`pii`), plus PESEL, NIP, REGON, IBAN, klucze API i sekrety.
2. **Klasyfikator Laya Experts · pii** — 22 etykiety (imię, telefon, karta, …) albo heurystyka, gdy wagi nie są pobrane.
3. **Reguły twarde** — poprawny PESEL / NIP, Luhn karty, IBAN i sekrety zostają nawet gdy model powie `not pii`.
4. **Kategorie i ryzyko** — RODO / PCI-DSS / sekrety, potem akcja bramki: `allow` | `redact` | `block`.

```
tekst ──► finder spanów ──► Laya PII (albo heurystyka)
                │
                ▼
        kategorie + ryzyko ──► allow / redact / block ──► LLM / API
```

## Instalacja

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[all]
```

Bez PyTorch / wag Laya warstwa i tak działa (`backend="heuristic"`). Pełny model PII (~850 MB, `goku-san/laya-experts`, folder `pii`) wczytuje się przy `backend="laya"` albo `auto`, gdy pakiet `laya` jest zainstalowany.

```bash
pip install "laya>=0.3.6,!=0.3.7"
```

## Użycie

```python
from sensitive_guard import SensitiveDataLayer

layer = SensitiveDataLayer(backend="auto", locale="pl", region="PL")

scan = layer.scan(
    "Anna Kowalska, tel +48 600 100 200, PESEL 44051401359, mail anna@example.com"
)
print(scan.risk)       # critical
print(scan.action)     # block
print(scan.redacted)   # Anna Kowalska, tel [TELEFON], PESEL [PESEL], mail [EMAIL]
print(scan.categories) # contact, government_id, …
```

Przed wywołaniem modelu:

```python
protected = layer.protect(user_prompt, raise_on_block=True)
response = llm(protected.outbound)   # zredagowany tekst albo wyjątek SensitiveDataBlocked
```

CLI:

```bash
python -m sensitive_guard "Call me on +48 600 100 200"
python -m sensitive_guard --file ticket.txt --json --protect
python -m sensitive_guard serve --port 8080
```

HTTP:

```bash
curl -s http://127.0.0.1:8080/v1/scan ^
  -H "Content-Type: application/json" ^
  -d "{\"text\":\"mail billing@acme.example\"}"
```

## Kategorie

| Kategoria | Przykłady | Ryzyko |
| --- | --- | --- |
| `person_name` | imię, nazwisko, tytuł | medium / low |
| `contact` | e-mail, telefon | medium |
| `location` | ulica, miasto, kod | medium / low |
| `government_id` | PESEL, NIP, paszport, dowód | critical / high |
| `financial` | karta, IBAN | critical |
| `credentials` | klucz API, token, hasło | critical |
| `demographic` | płeć, wiek | low |
| `temporal` | data, godzina | low |
| `online` | URL | low |

Ekspert PII jest trenowany na angielskim OpenPII. Dla polskiego tekstu finder + checksumy PESEL/NIP działają od razu; dokumentową politykę Laya (Router, 100+ języków) włączysz flagą `use_policy=True`.

## Testy

```bash
pip install pytest
pytest
```

## Kontrola sieci (branch `global_control`)

Nie tylko przeglądarka. Agenty i SDK firmy idą przez **bramkę** (`OPENAI_BASE_URL`) albo **HTTP proxy**. Opis: [NETWORK.md](NETWORK.md).

```bash
python -m sensitive_guard net --backend heuristic --port 8080 --proxy-port 8888
```

## Dashboard Helios Guard

React (Vite) w `dashboard/`. Dwa widoki (**Manager** / **Security**), PL/EN, routing po hashu z parametrami (linki do filtrów da się wkleić w slajd).

| Grupa | Strona | Co pokazuje |
|---|---|---|
| Monitor | Security posture | wynik 0-100, karty „dzisiaj”, słupki 24h, zespół / destynacja / kategoria, top osób, pole „sprawdź prompt”, pasek testów |
| Monitor | Incidents | kolejka z filtrami, grupowanie powtórek, akcje zbiorcze, eksport CSV/JSONL, szczegół z „dlaczego”, runbook, notatka, przypisanie |
| Monitor | Threats (security) | feed sygnatur OWASP LLM, import z CERT, liczniki loop / memory / tool / model |
| Monitor | Audit (security) | append-only `data/audit.jsonl`, filtry, maskowanie wartości, `reveal` zapisywany w audycie |
| Monitor | Telemetry (security) | p50/p95, RPM, backend split, błędy upstreamu, ostatnie decyzje |
| Govern | Controls | katalog deterministic / semantic z trafieniami, próg z podglądem na żywo, akcje per kategoria, nadpisania per destynacja, presety, allow-lista modeli |
| Govern | Policy | efektywna polityka, wersja, mtime, historia zmian, edycja i eksport `policy.json` |
| Govern | Budget | tokeny / koszt / RPM per osoba, zespół, model; 80 % alert; 429 |
| Govern | Roles / Categories / Whitelist / People | edycja, „co ta rola może wysłać”, własne wzorce regex dla kategorii, nieznani nadawcy |
| Demo | Agent chat | scenariusze jednym klikiem (PESEL, karta, klucz, injection, model, tool, pętla) przez bramkę `/net/openai` |
| Demo | Architecture | żywy status wejść (wtyczka / bramka / proxy / MITM) i potok kontroli |

```bash
python -m sensitive_guard serve --backend heuristic --port 8080
cd dashboard
npm install
npm run dev          # http://127.0.0.1:5173 (proxy do :8080)
npm run build        # dist/ serwowane przez bramkę pod http://127.0.0.1:8080/app
```

## Judge mode

Wszystko, co jury może zmienić w trakcie oceny, działa **bez restartu** i jest widoczne w dashboardzie od następnego żądania.

1. **Edytuj konfigurację na żywo.** `data/policy.json` jest przeładowywany po mtime. Zmień `threshold`, `category_actions`, `allowed_models` albo wyłącz kontrolkę w `controls` — baner „Policy reloaded (version N)” pojawi się w dashboardzie, a `GET /health` zwróci nową `policy_version`. To samo z UI: Controls → przełącznik / suwak / presety `strict | balanced | permissive`.
2. **Uruchom testy.** `pytest` (102 testy, pozytywne i negatywne dla każdej kontrolki: policy, budget, rate limit, signatures, model / tool allow-list, memory isolation, loop guard, skan odpowiedzi, audit, incydenty, telemetria). `tests/conftest.py` zapisuje wynik do `data/last_pytest.json`, który dashboard pokazuje w pasku statusu i na stronie Telemetry.
3. **Wrzuć własny prompt.** Pole na stronie Security posture woła `POST /v1/scan` i pokazuje akcję, encje, kontrolki i opóźnienie. Strona Agent chat przechodzi pełną ścieżką przez `/net/openai/v1/chat/completions` (403 blok, 429 budżet / pętla, 200 z redakcją). Bez klucza API upstream zwraca 502 — bramka i tak zablokowała wcześniej, co widać w nagłówkach `X-Helios-*`.
4. **Telemetria.** `GET /v1/admin/metrics` — postawa z listą odjęć, p50/p95, RPM, podział backendu, godzinowe słupki, per zespół / destynacja / kategoria / rodzaj. `GET /v1/admin/audit?format=csv` — pełny ślad decyzji (wartości zamaskowane; `reveal=true` jest logowany).
5. **Degradacja.** Bez `pip install sensitive-guard[laya]` bramka działa w trybie `heuristic` (deterministyczne: PESEL / NIP / IBAN / Luhn / sekrety / sygnatury) i mówi o tym banerem. Semantyczne kontrolki pokazują się jako wyłączone.

Ścieżka decyzji dla jednego żądania: allow-lista modeli → rate limit → budżet → loop guard → (tool allow-list, memory isolation w bramce) → finder + klasyfikator → sygnatury → własne wzorce → wyłączone kontrolki → whitelist / rola → akcja per kategoria / destynacja → redakcja → incydent (dedupe 5 min) → audit + telemetria.

Reset danych demo: Incidents (widok Security) → „Clear live incidents” / „Remove seed incidents”, albo `POST /v1/admin/demo/reset`.

## Wtyczka Chrome (czaty AI)

Rozszerzenie w `extension/` skanuje pole wiadomości na ChatGPT, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek i innych. Przed Enter / „Wyślij” woła `POST /v1/scan` i potrafi przerwać wysyłkę.

```bash
python -m sensitive_guard serve --backend heuristic --port 8080
```

Potem: `chrome://extensions` → tryb deweloperski → Załaduj rozpakowane → `extension/`.

Demo w przeglądarce bez wtyczki: http://127.0.0.1:8080/demo

Szczegóły: [extension/README.md](extension/README.md).

## Testy

```bash
pip install pytest
pytest
```

Demo bez pobierania wag:

```bash
python examples/demo.py
python examples/llm_gateway.py
```
