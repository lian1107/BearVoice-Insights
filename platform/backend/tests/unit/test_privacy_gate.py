from bearvoice.modules.ingest.privacy import sanitize_voice_text


def test_sanitize_voice_text_masks_address_and_phone_without_retaining_values():
    original = "按键无响应 / 省榆县街市场门口 / 联系13800138000"
    result = sanitize_voice_text(original)

    assert "省榆县街市场门口" not in result.text
    assert "13800138000" not in result.text
    assert "[地址已脱敏]" in result.text
    assert "[手机号已脱敏]" in result.text
    assert {finding.entity_type for finding in result.findings} == {
        "address",
        "phone",
    }
    assert all(not hasattr(finding, "matched_value") for finding in result.findings)
