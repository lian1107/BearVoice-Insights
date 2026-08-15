from bearvoice.observability import build_trace_attributes, redact_sensitive


def test_trace_attributes_exclude_prompt_and_customer_text():
    attributes = build_trace_attributes(
        run_id="run-1",
        phase="extract",
        provider="cache-only",
        model=None,
        input_hash="sha256:abc",
    )

    assert set(attributes) == {
        "run_id",
        "phase",
        "provider",
        "model",
        "input_hash",
    }


def test_redaction_removes_tokens_passwords_and_private_key_headers():
    secret = "ghp_" + "example-secret-value"
    message = f"token={secret} password=hello -----BEGIN PRIVATE KEY-----"
    redacted = redact_sensitive(message)

    assert secret not in redacted
    assert "password=hello" not in redacted
    assert "BEGIN PRIVATE KEY" not in redacted
