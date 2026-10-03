# Wtyczka Chrome

Skanuje **pole wiadomości** na najpopularniejszych czatach AI i przed Enter / „Wyślij” woła lokalną warstwę Laya. Nie podszywa się pod protokół Messengera i nie czyta całego ruchu TLS.

## Strony

ChatGPT, Claude, Gemini, AI Studio, NotebookLM, Copilot, Bing Chat, Perplexity, Poe, HuggingChat, Grok, DeepSeek, Mistral, You.com, Character.AI, Meta AI, Duck.ai, LM Arena, Groq, OpenRouter, Kimi, Qwen, Phind, Pi, ChatPDF.

Na każdej z nich wtyczka bierze tekst z `textarea` / `contenteditable` / `role=textbox` i tyle.

## Instalacja

1. Uruchom warstwę:

```bash
python -m sensitive_guard serve --backend heuristic --port 8080
```

2. Chrome → `chrome://extensions` → tryb deweloperski → **Załaduj rozpakowane** → katalog `extension/`.
3. Wejdź na ChatGPT / Claude / Gemini. W prawym dolnym rogu jest znacznik `guard`.
4. Wpisz PESEL albo e-mail i naciśnij Enter. Wysyłka staje, widać kategorie i wersję z maskami.

## Demo bez wtyczki

Po starcie serwera: [http://127.0.0.1:8080/demo](http://127.0.0.1:8080/demo)

## Zachowanie

| Werdykt Laya | Co robi wtyczka |
| --- | --- |
| `allow` | puszcza Enter / klik |
| `redact` | zatrzymuje; można wysłać tekst z `[PESEL]`, `[EMAIL]`… |
| `block` | zatrzymuje; sekrety i identyfikatory krytyczne nie wychodzą |

Popup: włącz/wyłącz, próg, „blokuj gdy API leży”, adres `http://127.0.0.1:8080`.
