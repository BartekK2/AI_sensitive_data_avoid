from sensitive_guard.taxonomy import (
    GateAction,
    RiskLevel,
    SensitivityCategory,
    action_for_risk,
    category_for,
    redact_token,
    risk_for,
)


def test_mappings():
    assert category_for("pesel") is SensitivityCategory.GOVERNMENT_ID
    assert risk_for("api key") is RiskLevel.CRITICAL
    assert risk_for("email address") is RiskLevel.MEDIUM
    assert action_for_risk(RiskLevel.CRITICAL) is GateAction.BLOCK
    assert action_for_risk(RiskLevel.MEDIUM) is GateAction.REDACT
    assert action_for_risk(RiskLevel.LOW) is GateAction.ALLOW
    assert action_for_risk(RiskLevel.LOW, strict=True) is GateAction.REDACT


def test_redact_tokens_locale():
    assert redact_token("pesel", "pl") == "PESEL"
    assert redact_token("given name", "pl") == "IMIĘ"
    assert redact_token("email address", "en") == "EMAIL"
