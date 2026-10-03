from sensitive_guard.finder import luhn_ok, nip_checksum_ok, pesel_checksum_ok, propose_spans


def test_proposes_email_and_phone():
    text = "Call Jane at +48 600 100 200 or jane.doe@example.com"
    spans = propose_spans(text)
    families = {text[start:end]: names for (start, end), names in spans.items()}
    assert any("EMAIL" in names for names in families.values())
    assert any("PHONE" in names or "PHONE_RUN" in names for names in families.values())


def test_proposes_pesel_and_api_key():
    text = "PESEL 44051401359 key sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    spans = propose_spans(text)
    flat = [name for names in spans.values() for name in names]
    assert "PESEL" in flat
    assert "API_KEY" in flat


def test_glued_pesel_after_name():
    spans = propose_spans("maciej stadler05050202911")
    flat = [name for names in spans.values() for name in names]
    assert "PESEL" in flat


def test_checksums():
    assert pesel_checksum_ok("44051401359")
    assert not pesel_checksum_ok("44051401358")
    assert nip_checksum_ok("123-456-32-18")
    assert not nip_checksum_ok("123-456-32-19")
    assert luhn_ok("4111111111111111")
    assert not luhn_ok("4111111111111112")
