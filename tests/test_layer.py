from sensitive_guard import GateAction, RiskLevel, SensitivityCategory, SensitiveDataLayer


def layer() -> SensitiveDataLayer:
    return SensitiveDataLayer(backend="heuristic", locale="pl", region="PL")


def test_scan_categorizes_contact_and_id():
    text = "Anna Kowalska, tel +48 600 100 200, mail anna.kowalska@example.com, PESEL 44051401359"
    scan = layer().scan(text)
    labels = {entity.label for entity in scan.entities}
    assert "email address" in labels
    assert "phone number" in labels
    assert "pesel" in labels
    assert "person name" in labels
    assert scan.risk is RiskLevel.CRITICAL
    assert scan.action is GateAction.BLOCK
    categories = {item.category for item in scan.categories}
    assert SensitivityCategory.CONTACT in categories
    assert SensitivityCategory.GOVERNMENT_ID in categories
    assert SensitivityCategory.PERSON_NAME in categories
    assert "[EMAIL]" in scan.redacted or "[email" in scan.redacted.lower()
    assert "44051401359" not in scan.redacted
    assert "anna.kowalska@example.com" not in scan.redacted


def test_protect_blocks_secrets():
    text = "export OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz012345"
    result = layer().protect(text)
    assert result.action is GateAction.BLOCK
    assert result.outbound is None
    assert any(entity.category is SensitivityCategory.CREDENTIALS for entity in result.scan.entities)


def test_protect_redacts_medium_risk():
    text = "Please reply to billing@acme.example"
    result = layer().protect(text)
    assert result.action is GateAction.REDACT
    assert result.outbound is not None
    assert "billing@acme.example" not in result.outbound


def test_allow_clean_text():
    text = "Please refund the duplicate invoice from March."
    scan = layer().scan(text)
    assert scan.action is GateAction.ALLOW
    assert scan.risk is RiskLevel.NONE
    assert scan.redacted == text


def test_card_and_iban():
    text = "Card 4111111111111111 IBAN PL61109010140000071219812874"
    scan = layer().scan(text)
    labels = {entity.label for entity in scan.entities}
    assert "credit card number" in labels
    assert "iban" in labels
    assert scan.action is GateAction.BLOCK


def test_json_roundtrip():
    scan = layer().scan("mail test.user@example.org")
    payload = scan.model_dump()
    assert payload["entities"][0]["label"] == "email address"


def test_name_span_does_not_swallow_contraction():
    scan = layer().scan("Hi, I'm Priya Nair.")
    names = [entity.text for entity in scan.entities if entity.label == "person name"]
    assert names == ["Priya Nair"]


def test_pesel_from_context_even_if_short_or_invalid():
    scan = layer().scan("dosłownie napisałem pesel: 0828282")
    assert any(entity.label == "pesel" and "0828282" in entity.text for entity in scan.entities)
    assert not any(entity.label == "phone number" and "0828282" in entity.text for entity in scan.entities)


def test_eleven_digit_pesel_is_not_phone():
    scan = layer().scan("klient 44051401358")
    labels = {entity.text: entity.label for entity in scan.entities}
    assert labels.get("44051401358") == "pesel"
    assert "phone number" not in labels.values() or all(
        entity.label != "phone number" or not entity.text.isdigit() for entity in scan.entities
    )


def test_api_key_not_phone():
    scan = layer().scan("API-KEY to sk-proj-abcdefghijklmnopqrstuvwxyz012345")
    assert any(entity.label == "api key" for entity in scan.entities)
    assert not any(entity.label == "phone number" and "sk-proj" in entity.text for entity in scan.entities)


def test_labeled_numeric_secret_is_not_phone():
    scan = layer().scan("api-key: 182736451823")
    assert any(entity.label == "api key" and "182736451823" in entity.text for entity in scan.entities)
    assert not any(entity.label == "phone number" for entity in scan.entities)


def test_real_phone_still_detected():
    scan = layer().scan("zadzwoń na +48 600 100 200")
    assert any(entity.label == "phone number" for entity in scan.entities)
