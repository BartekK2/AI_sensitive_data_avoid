import json
import socket
import threading

from sensitive_guard.netgate import decode_payload, inspect_and_maybe_redact
from sensitive_guard.tlsca import ensure_ca, issue_host_cert
from sensitive_guard.tlsmitm import is_prompt_rpc, read_request, relay_http11, should_intercept


def test_intercepts_antigravity_not_cursor():
    assert should_intercept("daily-cloudcode-pa.googleapis.com")
    assert should_intercept("cloudcode-pa.googleapis.com")
    assert should_intercept("generativelanguage.googleapis.com")
    assert should_intercept("api.openai.com")
    assert not should_intercept("api3.cursor.sh")
    assert not should_intercept("accounts.google.com")
    assert not should_intercept("www.messenger.com")
    assert is_prompt_rpc("/v1internal:streamGenerateContent?alt=sse")
    assert not is_prompt_rpc("/v1internal:loadCodeAssist")


def test_ca_issues_leaf(tmp_path):
    ca, key = ensure_ca(tmp_path)
    assert ca.exists() and key.exists()
    cert, host_key = issue_host_cert("cloudcode-pa.googleapis.com", tmp_path)
    assert "BEGIN CERTIFICATE" in cert.read_text(encoding="ascii")
    assert host_key.exists()


def test_decode_scans_google_field_names():
    raw = json.dumps(
        {"request": {"userInput": "pesel 44051401359 i zrob CV"}, "project": "x"}
    ).encode()
    text, payload = decode_payload(raw, "application/json")
    assert payload is not None
    assert "44051401359" in text


def test_relay_blocks_pesel_before_upstream():
    client_a, client_b = socket.socketpair()
    up_a, up_b = socket.socketpair()
    blocked = {"n": 0}

    def inspect(body, _ctype, _emp, _host):
        if b"44051401359" in body:
            blocked["n"] += 1
            return {"action": "block", "scan": {"action": "block"}}
        return {"action": "allow"}

    def serve():
        try:
            relay_http11(client_b, "cloudcode-pa.googleapis.com", inspect, upstream=up_a)
        except OSError:
            pass

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    body = b'{"text":"pesel 44051401359"}'
    client_a.sendall(
        b"POST /v1internal:streamGenerateContent HTTP/1.1\r\n"
        b"Host: cloudcode-pa.googleapis.com\r\n"
        b"Content-Type: application/json\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        + body
    )
    client_a.settimeout(3)
    raw = b""
    try:
        while b"\r\n\r\n" not in raw or len(raw) < 40:
            chunk = client_a.recv(4096)
            if not chunk:
                break
            raw += chunk
    except TimeoutError:
        pass
    up_b.settimeout(0.2)
    leaked = b""
    try:
        leaked = up_b.recv(4096)
    except (TimeoutError, OSError):
        leaked = b""
    client_a.close()
    client_b.close()
    up_a.close()
    up_b.close()
    assert blocked["n"] == 1
    assert b"403" in raw
    assert b"sensitive_data_blocked" in raw
    assert leaked == b""


def test_read_request_content_length():
    left, right = socket.socketpair()
    payload = b"hello-body"
    left.sendall(
        b"POST /x HTTP/1.1\r\nHost: h\r\n"
        + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
        + payload
    )
    line, _head, body = read_request(right)
    left.close()
    right.close()
    assert line.startswith(b"POST /x")
    assert body == payload


def _gate(tmp_path, payload, destination):
    from sensitive_guard.layer import SensitiveDataLayer
    from sensitive_guard.workspace import WorkspaceStore, execute_gated_scan, seed

    store = WorkspaceStore(tmp_path / "ws.json")
    store._write(seed())
    layer = SensitiveDataLayer(backend="heuristic")
    return inspect_and_maybe_redact(
        json.dumps(payload).encode(),
        "application/json",
        lambda body: execute_gated_scan(layer, store, body),
        None,
        destination,
    )


def test_inspect_blocks_weird_json_key(tmp_path):
    gated = _gate(tmp_path, {"userInput": "pesel: 44051401359"}, "cloudcode-pa.googleapis.com")
    assert gated["action"] == "block"


def test_siema_not_blocked_when_metadata_has_dates(tmp_path):
    payload = {
        "project": "aicode-consumers",
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "<USER_REQUEST>\nSiema\n</USER_REQUEST>\n"
                                "<ADDITIONAL_METADATA>\nThe current local time is: 2026-10-03 14:10.\n"
                                "See https://antigravity.google/docs\n</ADDITIONAL_METADATA>"
                            )
                        }
                    ],
                }
            ]
        },
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "allow"
    assert json.loads(gated["body"]) == payload


def test_glued_pesel_without_label_is_blocked(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\nmaciej stadler05050202911\n</USER_REQUEST>"}],
                }
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "block"


def test_user_request_pesel_still_blocked(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\nMaciej Stadler pesel 44051401359\n</USER_REQUEST>"}],
                }
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "block"


def test_later_siema_turn_not_blocked_by_old_pesel(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\npesel 44051401359\n</USER_REQUEST>"}],
                },
                {"role": "model", "parts": [{"text": "nie moge"}]},
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\nSiema\n</USER_REQUEST>"}],
                },
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "allow"


def test_system_prompt_does_not_hide_the_user_number(tmp_path):
    system = (
        "<identity>\nYou are Antigravity, a powerful agentic AI coding assistant.\n"
        "User requests are enclosed within <USER_REQUEST> tags.\n</identity>"
    )
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\nmaciej stadler 05261678389\n</USER_REQUEST>"}],
                },
                {"role": "user", "parts": [{"text": system}]},
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "block"
    assert "05261678389" in gated["texts"][0]


def test_ten_digit_number_with_name_is_blocked(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": "<USER_REQUEST>\nmaciej stadler 0525810102\n</USER_REQUEST>"}],
                }
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["action"] == "block"


def test_block_names_the_windows_user_and_repo(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "<user_information>\n"
                                "The USER's OS version is windows.\n"
                                "c:\\Users\\barte\\Desktop\\AI_hackyeah -> BartekK2/AI_sensitive_data_avoid\n"
                                "</user_information>\n"
                                "<USER_REQUEST>\nmaciej stadler 05261678389\n</USER_REQUEST>"
                            )
                        }
                    ],
                }
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    incident = gated["scan"]["incident"]
    assert gated["action"] == "block"
    assert incident["employee_name"] == "barte (BartekK2)"
    assert incident["team"] == "BartekK2/AI_sensitive_data_avoid"
    assert "05261678389" not in incident["redacted"]


def test_known_email_maps_to_employee(tmp_path):
    payload = {
        "request": {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "<user_information>\nanna.nowak@helios.pl\n</user_information>\n"
                                "<USER_REQUEST>\npesel 44051401359\n</USER_REQUEST>"
                            )
                        }
                    ],
                }
            ]
        }
    }
    dest = "daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse"
    gated = _gate(tmp_path, payload, dest)
    assert gated["scan"]["incident"]["employee_name"] == "Anna Nowak"
    assert gated["scan"]["incident"]["team"] == "Support"


def test_skips_session_rpcs(tmp_path):
    gated = _gate(
        tmp_path,
        {"userInput": "pesel: 44051401359"},
        "daily-cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
    )
    assert gated["action"] == "allow"
