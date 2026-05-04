"""Unit tests for src/utils/secrets_client.py."""

from unittest.mock import MagicMock, patch

import pytest

from src.utils import secrets_client


@pytest.fixture()
def mock_sm():
    with patch.object(secrets_client, "_get_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestGetSecret:
    def test_returns_dict_for_json_secret(self, mock_sm):
        mock_sm.get_secret_value.return_value = {
            "SecretString": '{"api_key": "abc123", "endpoint": "https://example.com"}',
        }

        result = secrets_client.get_secret("my-secret")

        assert isinstance(result, dict)
        assert result["api_key"] == "abc123"

    def test_returns_string_for_plain_secret(self, mock_sm):
        mock_sm.get_secret_value.return_value = {
            "SecretString": "plain-text-secret-value",
        }

        result = secrets_client.get_secret("my-plain-secret")

        assert isinstance(result, str)
        assert result == "plain-text-secret-value"
