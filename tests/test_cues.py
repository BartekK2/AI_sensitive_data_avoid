from sensitive_guard.cues import cue_label, looks_like_phone, propose_labeled_spans


def test_cue_before_span():
    assert cue_label("napisałem pesel: ") == "pesel"
    assert cue_label("API-KEY to ") == "api key"
    assert cue_label("secret: ") == "api key"
    assert cue_label("zadzwoń na ") is None


def test_phone_shape():
    assert looks_like_phone("+48 600 100 200")
    assert looks_like_phone("600100200")
    assert not looks_like_phone("44051401359")
    assert not looks_like_phone("sk-proj-abcd1234")
    assert not looks_like_phone("0828282")


def test_labeled_pesel_span():
    spans = propose_labeled_spans("pesel: 0828282 i nic więcej")
    values = [slice_ for slice_ in spans]
    assert any(end - start >= 6 for start, end in values)
