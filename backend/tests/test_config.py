"""The mock switches gate real spend and real AWS calls, so their defaults
matter more than most config.
"""

import importlib

import pytest


@pytest.fixture
def settings_with(monkeypatch):
    """Reload config under a given environment."""

    def _build(**env):
        for key in ("MOCK_AWS", "MOCK_BEDROCK", "USE_DYNAMODB"):
            monkeypatch.delenv(key, raising=False)
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        import app.config

        importlib.reload(app.config)
        return app.config.settings

    yield _build

    # Leave the module in the state the rest of the suite expects.
    monkeypatch.setenv("MOCK_AWS", "true")
    import app.config

    importlib.reload(app.config)


def test_defaults_are_safe(settings_with):
    """No configuration at all must not spend money or call AWS."""
    s = settings_with()
    assert s.mock_bedrock is True
    assert s.use_dynamodb is False


def test_mock_aws_false_enables_real_model(settings_with):
    s = settings_with(MOCK_AWS="false")
    assert s.mock_bedrock is False


def test_dynamodb_stays_off_unless_asked(settings_with):
    """The table only exists after a CDK deploy, so MOCK_AWS=false alone must
    not point the cache at a table that isn't there."""
    s = settings_with(MOCK_AWS="false")
    assert s.use_dynamodb is False

    s = settings_with(MOCK_AWS="false", USE_DYNAMODB="true")
    assert s.use_dynamodb is True


def test_bedrock_switch_overrides_master(settings_with):
    """Real AI with an in-memory cache is the useful middle state."""
    s = settings_with(MOCK_AWS="true", MOCK_BEDROCK="false")
    assert s.mock_bedrock is False
    assert s.use_dynamodb is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_truthy_spellings(settings_with, raw):
    assert settings_with(MOCK_BEDROCK=raw).mock_bedrock is True


@pytest.mark.parametrize("raw", ["0", "false", "False", "no", "off", ""])
def test_falsy_spellings(settings_with, raw):
    assert settings_with(MOCK_BEDROCK=raw).mock_bedrock is False
