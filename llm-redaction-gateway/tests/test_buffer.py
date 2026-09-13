from llm_gateway.buffer import HoldbackBuffer


def test_email_redacted_even_when_split_across_appends():
    buffer = HoldbackBuffer()
    buffer.append("Sure, my email is sumant")
    buffer.append("h@gmail")
    buffer.append(".com")
    result = buffer.flush()
    assert result == "Sure, my email is [REDACTED]"
