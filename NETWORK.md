# global_control — kontrola ruchu AI w firmie

To nie jest „podszywanie się pod Messenger”. To **firmowa bramka wyjściowa**:
agenty, skrypty i aplikacje nie wołają OpenAI / Claude / Gemini same z siebie.
Wołają Helios, Helios skanuje prompt Layą, i dopiero potem puszcza request.

```
LangChain / OpenAI SDK / cron / agent
        │
        │  OPENAI_BASE_URL=http://127.0.0.1:8080/net/openai/v1
        │  albo HTTP_PROXY=http://127.0.0.1:8888
        ▼
 Helios Net Gate  (Laya + role + whitelist + incydenty)
        │
        ▼
 api.openai.com / api.anthropic.com / …
```

## Dwie warstwy (tak się to nazywa)

| Nazwa | Po co | Co widzi |
| --- | --- | --- |
| **API gateway** (`/net/openai`, `/net/anthropic`, …) | Agenty i SDK | Cały JSON promptu |
| **HTTP forward proxy** (`:8888`) | Aplikacje z `HTTP_PROXY` | Ciało po HTTP; po HTTPS tylko host (SNI) |

HTTPS bez instalowania firmowego CA nie da się czytać (szyfr). Dlatego agenty
AI ustawiają `OPENAI_BASE_URL` na nas — to jest standard w korporacjach
(Zscaler / Netskope analogicznie, tylko my jesteśmy pod AI).

## Start

```bash
python -m sensitive_guard net --backend heuristic --port 8080 --proxy-port 8888
```

## Agent / skrypt

```bash
set OPENAI_BASE_URL=http://127.0.0.1:8080/net/openai/v1
set OPENAI_API_KEY=sk-...
set HTTP_PROXY=http://127.0.0.1:8888
set HTTPS_PROXY=http://127.0.0.1:8888
```

Python:

```python
from openai import OpenAI
client = OpenAI(
    base_url="http://127.0.0.1:8080/net/openai/v1",
    default_headers={"X-Employee-Id": "emp_anna"},
)
client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "pesel: 0828282"}],
)
# → HTTP 403 sensitive_data_blocked, wpis w dashboardzie menago
```

Claude:

```bash
set ANTHROPIC_BASE_URL=http://127.0.0.1:8080/net/anthropic
```

## Czego to nie robi

Nie łamie pinningu Messengera / WhatsApp. Tam nie ma `OPENAI_BASE_URL`.
Do czatów w przeglądarce zostaje wtyczka z `main`.

## Dashboard

Ten sam proces serwuje `/v1/admin` — [http://localhost:5173](http://localhost:5173)
pokazuje incydent gdy agent spróbuje wypchnąć PESEL.
