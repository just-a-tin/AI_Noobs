"""Provider errors must reach the badge as something actionable.

The raw text — "The security token included in the request is expired" —
tells a user nothing about what to do. Temporary SSO credentials expire within
hours, so this is the failure an operator hits most often.
"""

import pytest

from app.main import explain_failure


@pytest.mark.parametrize(
    "raw,expected",
    [
        (
            "Error code: 403 - {'message': 'The security token included in the "
            "request is expired'}",
            "credentials have expired",
        ),
        (
            "anthropic.claude-opus-5 is not available for this account.",
            "not entitled",
        ),
        (
            "not authorized to perform: bedrock-mantle:CreateInference ... with "
            "an explicit deny in a service control policy",
            "service control policy",
        ),
        ("ThrottlingException: Too many requests", "rate limiting"),
    ],
)
def test_known_failures_get_a_remedy(raw, expected):
    assert expected in explain_failure(Exception(raw))


def test_unknown_failure_keeps_the_original_text():
    """Never swallow an error we don't recognise."""
    message = explain_failure(Exception("some novel provider fault"))
    assert "some novel provider fault" in message


def test_messages_stay_short_enough_for_a_badge():
    long = "x" * 5000
    assert len(explain_failure(Exception(long))) < 260
