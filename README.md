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

## Dashboard managera

React (Vite) w `dashboard/`: incydenty, role, kategorie, whitelist, przypisywanie ludzi.

```bash
python -m sensitive_guard serve --backend heuristic --port 8080
cd dashboard
npm install
npm run dev
```

Otwórz http://127.0.0.1:5173 — toast wskakuje, gdy pracownik wyśle PESEL z [demo czatu](http://127.0.0.1:8080/demo).

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
