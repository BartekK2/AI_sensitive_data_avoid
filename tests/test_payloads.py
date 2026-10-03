from sensitive_guard.payloads import extract_texts, rewrite_strings


def test_extracts_openai_messages():
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "PESEL 44051401359"},
        ],
    }
    texts = extract_texts(payload)
    assert "PESEL 44051401359" in texts
    assert "You are helpful." in texts


def test_rewrite_redacts_user_content():
    payload = {"messages": [{"role": "user", "content": "mail a@b.com"}]}
    out = rewrite_strings(payload, lambda value: value.replace("a@b.com", "[EMAIL]"))
    assert out["messages"][0]["content"] == "mail [EMAIL]"
