"""Build the readable PL/EN AegIs decks (no film-clip screenshots)."""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
W, H = Inches(13.333), Inches(7.5)

BG = RGBColor(0xF3, 0xEE, 0xE4)
CREAM = RGBColor(0xFF, 0xFA, 0xF3)
INK = RGBColor(0x1C, 0x19, 0x15)
MUTED = RGBColor(0x6F, 0x67, 0x5C)
GREEN = RGBColor(0x50, 0x8A, 0x8E)
PURPLE = RGBColor(0xAF, 0x78, 0xA2)
PINK = RGBColor(0xF3, 0xE8, 0xEE)
SOFT = RGBColor(0xEF, 0xE6, 0xD6)
LINE = RGBColor(0xDD, 0xD2, 0xBE)
WHITE = RGBColor(0xFF, 0xFA, 0xF3)
SERIF = "Georgia"
SANS = "Calibri"


def rgb(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()


def stroke(shape, color, pt=1):
    shape.line.color.rgb = color
    shape.line.width = Pt(pt)


def box(slide, l, t, w, h, fill, radius=0.1):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    rgb(s, fill)
    s.adjustments[0] = radius
    return s


def tf_run(p, text, size, color, bold=False, font=SANS):
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    run.font.name = font
    return run


def textbox(slide, l, t, w, h, blocks, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """blocks: list of (text, size, color, bold, font) or ('\\n',)."""
    sh = slide.shapes.add_textbox(l, t, w, h)
    tf = sh.text_frame
    tf.word_wrap = True
    try:
        tf._txBody.bodyPr.set("anchor", {MSO_ANCHOR.TOP: "t", MSO_ANCHOR.MIDDLE: "ctr", MSO_ANCHOR.BOTTOM: "b"}[anchor])
    except Exception:
        pass
    first = True
    for block in blocks:
        if first:
            p = tf.paragraphs[0]
            first = False
        else:
            p = tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(6)
        if not block:
            continue
        if isinstance(block[0], tuple):
            for piece in block:
                tf_run(p, *piece)
        else:
            tf_run(p, *block)
    return sh


def mark(slide, l, t, w, h, size=72):
    sh = slide.shapes.add_textbox(l, t, w, h)
    p = sh.text_frame.paragraphs[0]
    for piece, color in (("A", GREEN), ("eg", INK), ("I", PURPLE), ("s", INK)):
        tf_run(p, piece, size, color, False, SERIF)
    return sh


def logo(slide):
    mark(slide, Inches(0.5), Inches(0.22), Inches(2.2), Inches(0.4), size=20)


def foot(slide, n, total=18):
    textbox(
        slide,
        Inches(11.4),
        Inches(7.12),
        Inches(1.5),
        Inches(0.28),
        [(f"{n:02d} / {total:02d}", 11, MUTED, False)],
        align=PP_ALIGN.RIGHT,
    )


def blank(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    fill = slide.background.fill
    fill.solid()
    fill.fore_color.rgb = BG
    return slide


def heading(slide, kicker, title, n):
    logo(slide)
    textbox(slide, Inches(0.5), Inches(0.62), Inches(12), Inches(0.28), [(kicker.upper(), 11, GREEN, True)])
    textbox(slide, Inches(0.5), Inches(0.88), Inches(12.3), Inches(0.7), [(title, 30, INK, False, SERIF)])
    foot(slide, n)


def card(slide, l, t, w, h, fill=CREAM):
    s = box(slide, l, t, w, h, fill, 0.08)
    if fill == CREAM:
        stroke(s, LINE, 1)
    return s


def build(lang):
    pl = lang == "pl"
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    def T(a, b):
        return a if pl else b

    # 1 title
    s = blank(prs)
    textbox(s, Inches(1.2), Inches(1.85), Inches(11), Inches(0.35), [(T("warstwa kontroli na wyjściu do AI", "a control layer on the way out to AI").upper(), 12, GREEN, True)], align=PP_ALIGN.CENTER)
    mark(s, Inches(3.15), Inches(2.25), Inches(7), Inches(1.5), size=84)
    textbox(
        s,
        Inches(1.6),
        Inches(4.05),
        Inches(10.1),
        Inches(1.6),
        [(T(
            "Lokalna bramka między pracownikiem (albo agentem) a modelem. Prompt nie wychodzi z firmy, dopóki nie przejdzie kontroli.",
            "A local gateway between the employee (or an agent) and the model. The prompt does not leave the company until it has passed inspection.",
        ), 20, MUTED, False)],
        align=PP_ALIGN.CENTER,
    )
    foot(s, 1)

    # 2 agenda
    s = blank(prs)
    heading(s, T("spis", "contents"), T("Co jest w tej prezentacji", "What this deck covers"), 2)
    items = (
        [
            "Problem: AI w pracy i dane, które już wyciekają",
            "Dlaczego DLP, proxy i szkolenia nie wystarczą",
            "Czym jest AegIs i gdzie siada w ruchu",
            "Jak zapada decyzja: allow / redact / block",
            "Kategorie, pewność, role i ludzie",
            "Incydent: kto, co, kiedy, dlaczego",
            "Panel, zmiana polityki bez restartu",
            "Uruchomienie i granice produktu",
        ]
        if pl
        else [
            "The problem: AI at work and data that already leaks",
            "Why DLP, proxies and training are not enough",
            "What AegIs is and where it sits in the traffic",
            "How a decision is made: allow / redact / block",
            "Categories, confidence, roles and people",
            "The incident: who, what, when, why",
            "The dashboard, policy changes with no restart",
            "How to run it, and what we refuse to do",
        ]
    )
    for i, line in enumerate(items):
        y = Inches(1.7) + Inches(i * 0.58)
        textbox(s, Inches(0.6), y, Inches(0.7), Inches(0.4), [(f"{i+1:02d}", 18, GREEN, True)])
        textbox(s, Inches(1.4), y, Inches(11), Inches(0.45), [(line, 22, INK, False)])

    # 3 problem
    s = blank(prs)
    heading(s, T("problem", "problem"), T("Ludzie wklejają pracę do chata.", "People paste their work into chat."), 3)
    box(s, Inches(0.5), Inches(1.75), Inches(3.3), Inches(4.8), CREAM, 0.1)
    stroke(s.shapes[-1], LINE, 1)
    textbox(s, Inches(0.5), Inches(2.4), Inches(3.3), Inches(1.6), [("38%", 60, GREEN, True)], align=PP_ALIGN.CENTER)
    textbox(s, Inches(0.65), Inches(4.2), Inches(3.0), Inches(1.2), [(T("w pracy, do chata", "at work, into chat"), 18, MUTED, False)], align=PP_ALIGN.CENTER)
    paras = (
        [
            "Firmy wpuszczają ChatGPT, Copilota i agentów do codziennej roboty. Pracownik nie atakuje systemu. On się spieszy: recenzja commita, umowa, mail do klienta.",
            "Do pola wiadomości ląduje kod, tabela z HR, zrzut z CRM, folder z .env. Model jest poza firmą. Jak prompt wyjdzie, nie da się go wycofać.",
            "To nawyk, nie teoria RODO. AegIs zakłada, że nawyku nie wyćwiczysz — trzeba zatrzymać pakiet zanim opuści maszynę.",
        ]
        if pl
        else [
            "Companies let ChatGPT, Copilot and agents into the working day. The employee is not attacking the system. They are in a hurry: review a commit, summarise a contract, draft a client mail.",
            "The message box gets code, an HR sheet, a CRM export, a folder with .env. The model is outside the firm. Once the prompt leaves, you cannot pull it back.",
            "This is a habit, not a theoretical GDPR risk. AegIs assumes you will not train the habit away — you stop the packet before it leaves the machine.",
        ]
    )
    y = Inches(1.75)
    for p in paras:
        textbox(s, Inches(4.1), y, Inches(8.6), Inches(1.5), [(p, 17, INK, False)])
        y += Inches(1.55)

    # 4 scenario
    s = blank(prs)
    heading(s, T("scenariusz", "scenario"), T("Jeden wklejony folder.", "One pasted folder."), 4)
    textbox(
        s,
        Inches(0.5),
        Inches(1.65),
        Inches(12.3),
        Inches(0.85),
        [(T(
            "Kuba z frontendu prosi o recenzję commita. Model mówi: wklej diff albo wrzuć pliki. Kuba wrzuca cały katalog, bo nie chce mu się cenzurować.",
            "Jake on frontend asks for a commit review. The model says paste the diff or drop the files. Jake drops the whole directory. He does not want to redact.",
        ), 17, INK, False)],
    )
    cards = (
        [
            (T("sekret", "secret"), ".env", T("Token do bazy, Stripe, Slack. Po wklejeniu jest w historii chata. Rotacja to już gaszenie pożaru.", "Database, Stripe, Slack tokens. Once pasted they live in chat history. Rotation is already incident response.")),
            (T("osoba", "person"), T("Identyfikatory", "Identifiers"), T("PESEL, NIP, e-mail, telefon. Dla RODO to udostępnienie danych poza umowę powierzenia.", "National ID, tax number, email, phone. Under GDPR that is disclosure outside the processing agreement.")),
            (T("firma", "company"), T("Wynagrodzenia", "Payroll"), T("Arkusz z pensjami nie jest kontekstem do recenzji kodu. Jest dokumentem kadrowym w obcym modelu.", "A salary sheet is not context for a code review. It is an HR document in someone else’s model.")),
        ]
    )
    for i, (tag, title, body) in enumerate(cards):
        x = Inches(0.5) + Inches(i * 4.2)
        fill = PINK if i == 2 else CREAM
        card(s, x, Inches(2.7), Inches(4.0), Inches(3.9), fill)
        textbox(s, x + Inches(0.25), Inches(2.9), Inches(3.5), Inches(0.3), [(tag.upper(), 11, PURPLE if i == 2 else GREEN, True)])
        textbox(s, x + Inches(0.25), Inches(3.25), Inches(3.5), Inches(0.55), [(title, 20, INK, True)])
        textbox(s, x + Inches(0.25), Inches(3.9), Inches(3.5), Inches(2.3), [(body, 15, MUTED, False)])

    # 5 gap
    s = blank(prs)
    heading(s, T("luka", "the gap"), T("Dlaczego dotychczasowe narzędzia tego nie łapią", "Why the tools you already bought miss this"), 5)
    gaps = (
        [
            (T("DLP na mailu i pendrive", "DLP on mail and USB"), T("Widzi załącznik w Outlooku. Nie widzi pola na chatgpt.com ani okna agenta. Ruch idzie HTTPS-em, często z konta prywatnego.", "Sees an Outlook attachment. Does not see the composer on chatgpt.com or an agent window. Traffic is HTTPS, often from a personal account.")),
            (T("Proxy bez treści", "A proxy without a body"), T("Po HTTPS widać host (SNI), nie prompt. Czytanie ciała to CA i MITM — i tak nie wejdziesz w pinning konsumenckich czatów.", "On HTTPS you see the host (SNI), not the prompt. Reading the body means a CA and MITM — and you still will not break pinning on consumer chats.")),
            (T("Szkolenie i regulamin", "Training and a policy PDF"), T("Ludzie znają zakaz. Potem mają deadline. Jeden „wrzuć cały folder” obchodzi politykę, której nikt nie egzekwuje przy Enter.", "People know the ban. Then they have a deadline. One “here’s the whole folder” walks around a rule nobody enforces at Enter.")),
            (T("Agenty poza przeglądarką", "Agents outside the browser"), T("SDK, cron, LangChain wołają API wprost. Potrzebują OPENAI_BASE_URL albo firmowego proxy — tego samego silnika decyzji.", "SDKs, cron, LangChain call the API directly. They need OPENAI_BASE_URL or a company proxy — the same decision engine.")),
        ]
    )
    for i, (title, body) in enumerate(gaps):
        x, y = Inches(0.5) + Inches((i % 2) * 6.4), Inches(1.75) + Inches((i // 2) * 2.45)
        card(s, x, y, Inches(6.15), Inches(2.25))
        textbox(s, x + Inches(0.25), y + Inches(0.18), Inches(5.65), Inches(0.45), [(title, 18, INK, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.7), Inches(5.65), Inches(1.4), [(body, 15, MUTED, False)])

    # 6 definition
    s = blank(prs)
    heading(s, T("definicja", "definition"), T("AegIs jest bramką, nie kolejnym chatbotem.", "AegIs is a gateway, not another chatbot."), 6)
    textbox(
        s,
        Inches(0.5),
        Inches(1.65),
        Inches(12.3),
        Inches(0.7),
        [(T(
            "Siedzi między tym, kto pisze, a modelem. Każdy prompt jest sprawdzany lokalnie. Dopiero werdykt decyduje, czy cokolwiek poleci na zewnątrz.",
            "It sits between whoever writes and the model. Every prompt is checked locally. Only the verdict decides whether anything goes out.",
        ), 16, INK, False)],
    )
    steps = (
        [
            ("01", T("pracownik / skrypt", "employee / script"), T("Pisze w ChatGPT, Claude, albo woła API z kodu.", "Types in ChatGPT or Claude, or calls the API from code."), CREAM),
            ("02", T("bramka AegIs", "AegIs gateway"), T("Na tej maszynie: finder, klasyfikator, reguły, rola. Nic nie jedzie „do chmury, żeby sprawdzić”.", "On this machine: finder, classifier, rules, role. Nothing is uploaded to the cloud to be checked."), GREEN),
            ("03", T("model dostaje albo nic", "model gets it, or nothing"), T("Allow — oryginał. Redact — maski. Block — model nie dostaje promptu, panel dostaje incydent.", "Allow — original. Redact — masks. Block — the model never sees it; the dashboard gets an incident."), PINK),
        ]
    )
    for i, (num, title, body, fill) in enumerate(steps):
        x = Inches(0.5) + Inches(i * 4.2)
        card(s, x, Inches(2.5), Inches(4.0), Inches(3.7), fill)
        tc, tb = (WHITE, RGBColor(0xE7, 0xF0, 0xF0)) if fill == GREEN else (INK, MUTED)
        textbox(s, x + Inches(0.25), Inches(2.7), Inches(3.5), Inches(0.3), [(num, 12, tc if fill == GREEN else GREEN, True)])
        textbox(s, x + Inches(0.25), Inches(3.15), Inches(3.5), Inches(0.9), [(title, 20, tc, True)])
        textbox(s, x + Inches(0.25), Inches(4.15), Inches(3.5), Inches(1.8), [(body, 15, tb, False)])

    # 7 entries
    s = blank(prs)
    heading(s, T("wejścia", "entry points"), T("Trzy drogi, jeden silnik.", "Three doors, one engine."), 7)
    entries = (
        [
            (T("przeglądarka", "browser"), T("Wtyczka Chrome", "Chrome extension"), T("Czyta pole na ChatGPT, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek. Przed Enter woła POST /v1/scan i potrafi przerwać wysyłkę.", "Reads the composer on ChatGPT, Claude, Gemini, Copilot, Perplexity, Grok, DeepSeek. Before Enter it calls POST /v1/scan and can stop the send."), CREAM),
            (T("agenty / SDK", "agents / SDK"), T("Bramka API", "API gateway"), T("OPENAI_BASE_URL=http://127.0.0.1:8080/net/openai/v1 (tak samo Anthropic, Ollama). Skanuje JSON promptu, potem — jeśli wolno — puszcza upstream.", "OPENAI_BASE_URL=http://127.0.0.1:8080/net/openai/v1 (same idea for Anthropic, Ollama). Scans the prompt JSON, then forwards if allowed."), GREEN),
            (T("procesy", "processes"), T("HTTP proxy :8888", "HTTP proxy :8888"), T("Dla narzędzi z HTTP_PROXY. Po HTTP widać ciało. Po HTTPS bez CA — host. Agenty AI powinny iść BASE_URL-em, nie MITM-em wszystkiego.", "For tools with HTTP_PROXY. On HTTP you see the body. On HTTPS without a CA — the host. Agents should use BASE_URL, not MITM-the-world."), CREAM),
        ]
    )
    for i, (tag, title, body, fill) in enumerate(entries):
        x = Inches(0.5) + Inches(i * 4.2)
        card(s, x, Inches(1.75), Inches(4.0), Inches(5.0), fill)
        tc, tb = (WHITE, RGBColor(0xE7, 0xF0, 0xF0)) if fill == GREEN else (INK, MUTED)
        textbox(s, x + Inches(0.25), Inches(1.95), Inches(3.5), Inches(0.3), [(tag.upper(), 11, tc if fill == GREEN else GREEN, True)])
        textbox(s, x + Inches(0.25), Inches(2.35), Inches(3.5), Inches(0.7), [(title, 20, tc, True)])
        textbox(s, x + Inches(0.25), Inches(3.15), Inches(3.5), Inches(3.3), [(body, 15, tb, False)])

    # 8 verdicts
    s = blank(prs)
    heading(s, T("werdykt", "verdict"), T("Trzy wyjścia z bramki", "Three ways out of the gate"), 8)
    vers = (
        [
            ("allow", T("Puść", "Pass"), T("Brak wrażliwych spanów albo rola / whitelist pozwala. Model dostaje oryginał. Zapis w audycie zostaje.", "No sensitive spans, or the role / whitelist allows it. The model gets the original. The audit line still exists."), CREAM),
            ("redact", T("Zredaguj", "Redact"), T("PESEL, e-mail, karta, telefon stają się maskami. Reszta idzie. Pracownik widzi, co ucięto, i może poprawić.", "IDs, email, card, phone become masks. The rest goes. The employee sees what was cut and can fix it."), SOFT),
            ("block", T("Zatrzymaj", "Stop"), T("Sekrety, identyfikatory krytyczne, jailbreak. Stop w UI, 403 w API. Model nie dostaje nic. Panel dostaje incydent.", "Secrets, critical IDs, jailbreak. Stop in the UI, 403 on the API. The model gets nothing. The dashboard gets an incident."), PINK),
        ]
    )
    for i, (tag, title, body, fill) in enumerate(vers):
        x = Inches(0.5) + Inches(i * 4.2)
        card(s, x, Inches(1.75), Inches(4.0), Inches(4.2), fill)
        textbox(s, x + Inches(0.25), Inches(1.95), Inches(3.5), Inches(0.3), [(tag.upper(), 11, PURPLE if i == 2 else GREEN, True)])
        textbox(s, x + Inches(0.25), Inches(2.35), Inches(3.5), Inches(0.55), [(title, 22, INK, True)])
        textbox(s, x + Inches(0.25), Inches(3.05), Inches(3.5), Inches(2.6), [(body, 16, MUTED, False)])
    textbox(
        s,
        Inches(0.5),
        Inches(6.15),
        Inches(12.3),
        Inches(0.7),
        [(T(
            "Preset balanced: government_id, financial, credentials i attack → block; health → redact. Admin zmienia to suwakiem, nie deployem.",
            "Balanced preset: government_id, financial, credentials and attack → block; health → redact. An admin changes that with a slider, not a deploy.",
        ), 14, MUTED, False)],
    )

    # 9 detection
    s = blank(prs)
    heading(s, T("wykrywanie", "detection"), T("Jak w ogóle widzimy, że to PESEL", "How we know it is an ID number"), 9)
    rows = (
        [
            (T("Finder", "Finder"), T("Kandydaci: rodziny regex z treningu Laya (pii) plus PESEL, NIP, REGON, IBAN, klucze, tokeny, hasła.", "Candidates: Laya pii regex families plus PESEL, NIP, REGON, IBAN, keys, tokens, passwords.")),
            (T("Laya · pii", "Laya · pii"), T("Otwarty klasyfikator (Apache-2.0). 22 etykiety, skalibrowane prawdopodobieństwa. Nie generuje tekstu i nie wysyła treści do zamkniętego API.", "Open decision classifier (Apache-2.0). 22 labels, calibrated probabilities. Does not generate text and does not send content to a closed API.")),
            (T("Reguły twarde", "Hard rules"), T("Poprawny PESEL / NIP, Luhn, IBAN i sekrety zostają nawet gdy model powie not pii. Checksumy nie są opinią.", "A valid PESEL / NIP, Luhn, IBAN and secrets stay even when the classifier says not pii. Checksums are not an opinion.")),
            (T("Sygnatury", "Signatures"), T("Jailbreak, injection, eksfiltracja, nadużycie narzędzi — katalog OWASP LLM, import CERT, włączany per kontrolka.", "Jailbreak, injection, exfiltration, tool abuse — OWASP LLM catalogue, CERT import, toggled per control.")),
            (T("Heurystyka", "Heuristic"), T("Bez wag (~850 MB) bramka wstaje: backend=heuristic. Semantyka jest wyłączona, reszta działa. Na laptopie sędziego to ten sam produkt.", "Without weights (~850 MB) the gate boots: backend=heuristic. Semantics show as off; the rest works. Same product on a judge’s laptop.")),
        ]
    )
    for i, (title, body) in enumerate(rows):
        y = Inches(1.68) + Inches(i * 0.95)
        card(s, Inches(0.5), y, Inches(12.3), Inches(0.88))
        textbox(s, Inches(0.7), y + Inches(0.18), Inches(2.3), Inches(0.55), [(title, 15, INK, True)])
        textbox(s, Inches(3.1), y + Inches(0.16), Inches(9.4), Inches(0.62), [(body, 14, MUTED, False)])

    # 10 categories
    s = blank(prs)
    heading(s, T("polityka · kategorie", "policy · categories"), T("Admin układa, co jest czym — i jak pewnie.", "Admin decides what counts — and how sure."), 10)
    textbox(
        s,
        Inches(0.5),
        Inches(1.65),
        Inches(12.3),
        Inches(0.7),
        [(T(
            "Kategoria ma ryzyko, akcję i próg pewności. Laya ocenia span; poniżej suwaka kategoria nie strzela. Własne kategorie dodajesz w panelu. policy.json przeładowuje się po mtime.",
            "A category has a risk, an action and a confidence floor. Laya scores the span; below the slider it does not fire. Custom categories are added in the panel. policy.json reloads on mtime.",
        ), 15, INK, False)],
    )
    table = (
        [
            ("government_id", T("PESEL, NIP, paszport, dowód", "national ID, tax number, passport"), "block"),
            ("credentials", T("klucz API, token, hasło", "API key, token, password"), "block"),
            ("financial", T("karta (Luhn), IBAN", "card (Luhn), IBAN"), "block"),
            ("attack", T("jailbreak, injection, eksfiltracja", "jailbreak, injection, exfiltration"), "block"),
            ("health", T("historia choroby", "medical history"), "redact"),
            ("contact / person_name", T("e-mail, telefon, imię — zależy od destynacji i roli", "email, phone, name — depends on destination and role"), T("zależnie", "depends")),
        ]
    )
    for i, (cat, ex, act) in enumerate(table):
        y = Inches(2.45) + Inches(i * 0.7)
        card(s, Inches(0.5), y, Inches(12.3), Inches(0.62), SOFT if i % 2 == 0 else CREAM)
        textbox(s, Inches(0.7), y + Inches(0.12), Inches(3.2), Inches(0.4), [(cat, 15, INK, True)])
        textbox(s, Inches(4.0), y + Inches(0.12), Inches(6.2), Inches(0.4), [(ex, 14, MUTED, False)])
        textbox(s, Inches(10.4), y + Inches(0.12), Inches(2.1), Inches(0.4), [(act, 14, GREEN, True)])

    # 11 roles
    s = blank(prs)
    heading(s, T("polityka · role", "policy · roles"), T("Rola to wyjątek, nie opis stanowiska.", "A role is an exception, not a job title."), 11)
    textbox(
        s,
        Inches(0.5),
        Inches(1.65),
        Inches(12.3),
        Inches(0.7),
        [(T(
            "Programista, lekarz i księgowa wyciekają czymś innym. Rola mówi: tej osobie wolno wysłać te kategorie. Ta sama kategoria może blokować developera i puszczać księgową.",
            "A developer, a doctor and an accountant leak different things. A role says: this person may send these categories. The same category can block a developer and allow an accountant.",
        ), 15, INK, False)],
    )
    roles = (
        [
            (T("Pracownik", "Employee"), T("brak wyjątków", "no exceptions"), T("Każda wycieczka PII ląduje u managera. Domyślny stan nowej osoby.", "Any PII excursion lands with a manager. Default for a new person.")),
            ("HR", T("imię, kontakt, demografia", "name, contact, demographic"), T("Rekrutacja musi wkleić imię i telefon. PESEL nadal nie.", "Recruiting must paste a name and phone. National ID still no.")),
            (T("Finanse", "Finance"), "financial", T("IBAN kontrahenta albo karta testowa nie jest incydentem. Klucz API nadal jest.", "A vendor IBAN or test card is not an incident. An API key still is.")),
            ("Manager", T("wszystko + override", "everything + override"), T("Widzi dashboard i może nadpisać blokadę, gdy naprawdę trzeba.", "Sees the dashboard and can override a block when it is genuinely needed.")),
        ]
    )
    for i, (name, exc, why) in enumerate(roles):
        x, y = Inches(0.5) + Inches((i % 2) * 6.4), Inches(2.5) + Inches((i // 2) * 2.15)
        card(s, x, y, Inches(6.15), Inches(2.0))
        textbox(s, x + Inches(0.25), y + Inches(0.15), Inches(5.65), Inches(0.35), [(name, 18, INK, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.5), Inches(5.65), Inches(0.3), [(exc, 13, GREEN, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.9), Inches(5.65), Inches(0.9), [(why, 14, MUTED, False)])

    # 12 people
    s = blank(prs)
    heading(s, T("polityka · ludzie", "policy · people"), T("Przypisanie działa od następnej wiadomości.", "Assignment applies on the next message."), 12)
    people = (
        [
            (T("Pracownicy", "People page"), T("E-mail, zespół, role_id. Wtyczka i bramka wiedzą kto pisze (konto / X-Employee-Id). Werdykt liczy się wobec tej roli.", "Email, team, role_id. The extension and gateway know who is typing (account / X-Employee-Id). The verdict is against that role."), CREAM),
            (T("Bez restartu", "No restart"), T("Zmieniasz Magdzie rolę z Pracownik na HR. Kolejny Enter idzie nową polityką. Baner pokazuje nową wersję. Bez reloadu wtyczki.", "Move Magda from Employee to HR. The next Enter already uses the new policy. The banner shows the new version. No extension reload."), GREEN),
            (T("Nieznany nadawca", "Unknown sender"), T("Konto spoza listy ląduje w kolejce „nieznani”. Nie znika w logach i nie dziedziczy wyjątków managera.", "An unknown account lands in the unknown queue. It does not vanish in the logs and does not inherit a manager’s exceptions."), CREAM),
            ("Whitelist", T("Wyjątki bez alarmu: adres testowy, konto firmowe, fałszywy alarm. Whitelist nie wyłącza reszty bramki.", "No-alert exceptions: a test address, a company account, a false positive. The whitelist does not switch the rest of the gate off."), PINK),
        ]
    )
    for i, (title, body, fill) in enumerate(people):
        x, y = Inches(0.5) + Inches((i % 2) * 6.4), Inches(1.75) + Inches((i // 2) * 2.45)
        card(s, x, y, Inches(6.15), Inches(2.25), fill)
        tc, tb = (WHITE, RGBColor(0xE7, 0xF0, 0xF0)) if fill == GREEN else (INK, MUTED)
        textbox(s, x + Inches(0.25), y + Inches(0.2), Inches(5.65), Inches(0.45), [(title, 18, tc, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.75), Inches(5.65), Inches(1.3), [(body, 15, tb, False)])

    # 13 incident
    s = blank(prs)
    heading(s, T("skutek", "outcome"), T("Blok bez incydentu to teatr.", "A block with no incident is theatre."), 13)
    textbox(
        s,
        Inches(0.5),
        Inches(1.65),
        Inches(12.3),
        Inches(0.55),
        [(T("Jak AegIs zatrzyma prompt, w dashboardzie powstaje rekord do przeczytania i reakcji.", "When AegIs stops a prompt, the dashboard gets a record you can read and act on."), 16, INK, False)],
    )
    left = (
        T("Kto — osoba, e-mail, zespół, rola.\nGdzie — chatgpt.com, OpenAI API, agent, proxy.\nCo — kategorie, etykiety, fragment z maskami.\nDlaczego — kontrolki, pewność, akcja.\nKiedy — czas i opóźnienie bramki.",
          "Who — person, email, team, role.\nWhere — chatgpt.com, OpenAI API, agent, proxy.\nWhat — categories, labels, a masked snippet.\nWhy — controls, confidence, action.\nWhen — timestamp and gate latency.")
    )
    right = (
        T("Kolejka z filtrami, grupowanie powtórek (dedupe 5 min).\nAkcje zbiorcze, przypisanie, notatka, runbook.\nEksport CSV / JSONL do audytu.\nWartości zamaskowane; reveal sam wpada do dziennika.",
          "A queue with filters, grouped repeats (5-minute dedupe).\nBulk actions, assignment, a note, a runbook.\nCSV / JSONL export for audit.\nValues stay masked; reveal itself is written to the log.")
    )
    card(s, Inches(0.5), Inches(2.35), Inches(6.15), Inches(3.7))
    textbox(s, Inches(0.75), Inches(2.55), Inches(5.7), Inches(0.4), [(T("Co jest w rekordzie", "What is in the record"), 18, INK, True)])
    textbox(s, Inches(0.75), Inches(3.1), Inches(5.7), Inches(2.7), [(left, 15, MUTED, False)])
    card(s, Inches(6.85), Inches(2.35), Inches(6.0), Inches(3.7))
    textbox(s, Inches(7.1), Inches(2.55), Inches(5.55), Inches(0.4), [(T("Co robi manager", "What a manager does"), 18, INK, True)])
    textbox(s, Inches(7.1), Inches(3.1), Inches(5.55), Inches(2.7), [(right, 15, MUTED, False)])

    # 14 dashboard
    s = blank(prs)
    heading(s, T("panel", "dashboard"), T("Wszystko, co jury może zmienić, widać od razu.", "Anything a judge can change is visible immediately."), 14)
    dash = (
        [
            (T("monitor", "monitor"), T("Postawa, incydenty, audit", "Posture, incidents, audit"), T("Wynik 0–100, karty dzisiaj, słupki 24h, top osób. Kolejka. Dziennik append-only. Telemetria p50/p95, RPM. Pole „sprawdź prompt” to ten sam /v1/scan.", "A 0–100 score, today cards, 24h bars, top people. The queue. Append-only log. Telemetry p50/p95, RPM. Check-a-prompt is the same /v1/scan."), CREAM),
            (T("govern", "govern"), T("Kontrolki i polityka", "Controls and policy"), T("Włącz checksumy, klasyfikator, sygnatury, role. Suwak progu. Akcja per kategoria i destynacja. Presety. Historia policy.json.", "Toggle checksums, classifier, signatures, roles. Threshold slider. Action per category and destination. Presets. History of policy.json."), CREAM),
            (T("na żywo", "live"), T("Następne żądanie, nie restart", "Next request, not a restart"), T("Zmiana threshold albo roli = banner Policy reloaded (version N). GET /health nowa wersja. Czat demo idzie przez /net/openai.", "Change the threshold or a role = Policy reloaded (version N). GET /health returns the new version. Demo chat walks /net/openai."), GREEN),
            (T("degradacja", "degradation"), T("Bez Laya też wstaje", "It still boots without Laya"), T("Brak wag = heurystyka + baner. PESEL / NIP / IBAN / Luhn / sekrety zostają. Semantyka jest szara, UI nie kłamie że model czuwa.", "No weights = heuristic + a banner. PESEL / NIP / IBAN / Luhn / secrets stay. Semantics go grey. The UI does not pretend a model is watching."), CREAM),
        ]
    )
    for i, (tag, title, body, fill) in enumerate(dash):
        x, y = Inches(0.5) + Inches((i % 2) * 6.4), Inches(1.7) + Inches((i // 2) * 2.5)
        card(s, x, y, Inches(6.15), Inches(2.3), fill)
        tc, tb = (WHITE, RGBColor(0xE7, 0xF0, 0xF0)) if fill == GREEN else (INK, MUTED)
        textbox(s, x + Inches(0.25), y + Inches(0.15), Inches(5.65), Inches(0.28), [(tag.upper(), 11, tc if fill == GREEN else GREEN, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.45), Inches(5.65), Inches(0.4), [(title, 17, tc, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.95), Inches(5.65), Inches(1.15), [(body, 14, tb, False)])

    # 15 local
    s = blank(prs)
    heading(s, T("lokalnie", "local"), T("Stop na maszynie. W ~28 ms.", "Stop on the machine. In ~28 ms."), 15)
    textbox(
        s,
        Inches(0.5),
        Inches(1.75),
        Inches(7.6),
        Inches(4.4),
        [(T(
            "Klasyfikacja nie jest round-tripem do dostawcy modelu. Finder i reguły twarde są tanie. Laya, jeśli włączona, liczy się lokalnie. Stąd dziesiątki milisekund, nie sekundy „skanujemy w chmurze”.\n\nTo ma znaczenie przy Enter i przy agencie, który czeka na tokeny. Bramka nie może być drugim modelem.\n\nJeśli werdykt to block — pakiet umiera tutaj. Nie ma „wyślemy, a potem zrobimy incident response”.",
            "Classification is not a round-trip to the model vendor. The finder and hard rules are cheap. Laya, if enabled, runs locally. Tens of milliseconds, not seconds of scanning in the cloud.\n\nThat matters on Enter and for an agent already waiting on tokens. The gate cannot be a second model.\n\nIf the verdict is block, the packet dies here. There is no send-it-and-do-IR-later.",
        ), 17, INK, False)],
    )
    card(s, Inches(8.4), Inches(1.75), Inches(4.4), Inches(4.6), GREEN)
    textbox(s, Inches(8.65), Inches(1.95), Inches(3.95), Inches(0.3), [(T("jedno żądanie", "one request").upper(), 11, RGBColor(0xD5, 0xEC, 0xEC), True)])
    textbox(
        s,
        Inches(8.65),
        Inches(2.4),
        Inches(3.95),
        Inches(3.7),
        [(T(
            "allow-lista modeli → rate limit → budżet → loop guard → finder + klasyfikator → sygnatury → wzorce → wyłączone kontrolki → whitelist / rola → akcja per kategoria → redakcja → incydent → audit + telemetria.",
            "model allow-list → rate limit → budget → loop guard → finder + classifier → signatures → patterns → disabled controls → whitelist / role → per-category action → redaction → incident → audit + telemetry.",
        ), 15, WHITE, False)],
    )

    # 16 limits
    s = blank(prs)
    heading(s, T("granice", "limits"), T("Czego świadomie nie robimy", "What we deliberately do not do"), 16)
    nos = (
        [
            (T("Nie łamiemy konsumenckich czatów", "We do not break consumer chats"), T("Brak MITM na Messengerze, WhatsAppie, pinned TLS. Do czatów AI w przeglądarce jest wtyczka, która czyta pole, nie cały TLS.", "No MITM on Messenger, WhatsApp, pinned TLS. For AI chats in the browser an extension reads the field, not the whole TLS session.")),
            (T("Nie jesteśmy DLP na wszystko", "We are not DLP for everything"), T("Nie zastępujemy antywirusa ani DLP na poczcie. Jesteśmy warstwą na wyjściu do modelu.", "We do not replace antivirus or mail DLP. We are a layer on the way out to a model.")),
            (T("Nie udajemy, że chmura sklasyfikuje lepiej", "We do not pretend the cloud classifies better"), T("Wysyłanie promptu do obcego API „żeby sprawdzić czy jest wrażliwy” jest tym samym wyciekiem.", "Sending the prompt to a third-party API to check if it is sensitive is the same leak.")),
            (T("Nie chowamy degradacji", "We do not hide degradation"), T("Bez Laya widać heurystykę. Bez klucza upstreamu bramka i tak zablokuje wcześniej — 502 nie maskuje 403.", "Without Laya you see heuristic. Without an upstream key the gate still blocks first — a 502 does not hide our 403.")),
        ]
    )
    for i, (title, body) in enumerate(nos):
        x, y = Inches(0.5) + Inches((i % 2) * 6.4), Inches(1.75) + Inches((i // 2) * 2.45)
        card(s, x, y, Inches(6.15), Inches(2.25), PINK if i == 3 else CREAM)
        textbox(s, x + Inches(0.25), y + Inches(0.2), Inches(5.65), Inches(0.6), [(title, 17, INK, True)])
        textbox(s, x + Inches(0.25), y + Inches(0.9), Inches(5.65), Inches(1.15), [(body, 15, MUTED, False)])

    # 17 start
    s = blank(prs)
    heading(s, T("start", "start"), T("Po clone — jedna komenda.", "After clone — one command."), 17)
    textbox(
        s,
        Inches(0.5),
        Inches(1.7),
        Inches(12.3),
        Inches(0.55),
        [(T("Na PATH: Python 3.10+ i Node 18+. Skrypt robi venv, zależności, build dashboardu, bramkę i proxy.", "On PATH: Python 3.10+ and Node 18+. The script does venv, dependencies, dashboard build, gate and proxy."), 16, INK, False)],
    )
    card(s, Inches(0.5), Inches(2.4), Inches(6.15), Inches(2.6), GREEN)
    textbox(s, Inches(0.75), Inches(2.6), Inches(5.7), Inches(0.35), [("python start.py", 22, WHITE, True)])
    textbox(s, Inches(0.75), Inches(3.15), Inches(5.7), Inches(1.6), [(T("Windows: py start.py albo .\\start.ps1. macOS / Linux: ./start.sh. Domyślnie heurystyka. --with-laya dociąga model.", "Windows: py start.py or .\\start.ps1. macOS / Linux: ./start.sh. Heuristic by default. --with-laya pulls the model."), 15, WHITE, False)])
    card(s, Inches(6.85), Inches(2.4), Inches(6.0), Inches(2.6))
    textbox(s, Inches(7.1), Inches(2.6), Inches(5.55), Inches(0.35), [(T("Adresy", "Addresses"), 20, INK, True)])
    textbox(s, Inches(7.1), Inches(3.15), Inches(5.55), Inches(1.6), [("http://127.0.0.1:8080/app\n/demo  /v1/scan  /net/openai/v1  :8888", 15, MUTED, False)])
    textbox(
        s,
        Inches(0.5),
        Inches(5.25),
        Inches(12.3),
        Inches(1.3),
        [(T(
            "Wtyczka: chrome://extensions → tryb deweloperski → Załaduj rozpakowane → katalog extension/. Potem ChatGPT / Claude / Gemini — przy PESEL-u Enter nie wychodzi.",
            "Extension: chrome://extensions → developer mode → Load unpacked → the extension/ folder. Then ChatGPT / Claude / Gemini — Enter on a national ID does not leave.",
        ), 16, INK, False)],
    )

    # 18 close
    s = blank(prs)
    mark(s, Inches(3.15), Inches(2.15), Inches(7), Inches(1.5), size=84)
    textbox(
        s,
        Inches(1.5),
        Inches(4.0),
        Inches(10.3),
        Inches(1.6),
        [(T(
            "Lokalna bramka. Prompt nie wychodzi, dopóki nie przejdzie kontroli. Polityka per kategoria i per rola. Incydent mówi kto i co — zanim model zdąży zobaczyć cokolwiek.",
            "A local gateway. The prompt does not leave until it has passed inspection. Policy per category and per role. The incident says who and what — before the model ever sees a thing.",
        ), 18, MUTED, False)],
        align=PP_ALIGN.CENTER,
    )
    foot(s, 18)

    out = ROOT / ("AegIs_pl.pptx" if pl else "AegIs_en.pptx")
    prs.save(out)
    print(out, "slides", len(prs.slides))


if __name__ == "__main__":
    build("pl")
    build("en")
