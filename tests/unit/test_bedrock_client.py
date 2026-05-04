"""Unit tests for src/utils/bedrock_client.py."""

import io
import json
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.utils import bedrock_client


@pytest.fixture()
def mock_bedrock():
    with patch.object(bedrock_client, "_get_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestInvokeClaude:
    def test_returns_text_response(self, mock_bedrock):
        body_payload = {"content": [{"text": "Hello from Claude"}]}
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(body_payload).encode()),
        }

        result = bedrock_client.invoke_claude("Say hello")

        assert result == "Hello from Claude"
        mock_bedrock.invoke_model.assert_called_once()

    def test_retries_on_throttling(self, mock_bedrock):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        success_body = {"content": [{"text": "OK"}]}
        mock_bedrock.invoke_model.side_effect = [
            throttle_error,
            {"body": io.BytesIO(json.dumps(success_body).encode())},
        ]

        with patch("src.utils.bedrock_client.time.sleep"):
            result = bedrock_client.invoke_claude("test")

        assert result == "OK"
        assert mock_bedrock.invoke_model.call_count == 2

    def test_raises_non_retryable_error(self, mock_bedrock):
        error = ClientError(
            {"Error": {"Code": "ValidationException", "Message": "Bad input"}},
            "InvokeModel",
        )
        mock_bedrock.invoke_model.side_effect = error

        with pytest.raises(ClientError):
            bedrock_client.invoke_claude("test")

    def test_raises_after_max_retries(self, mock_bedrock):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_bedrock.invoke_model.side_effect = [throttle_error] * 3

        with patch("src.utils.bedrock_client.time.sleep"):
            with pytest.raises(ClientError):
                bedrock_client.invoke_claude("test")

        assert mock_bedrock.invoke_model.call_count == 3


class TestInvokeClaudeMultimodal:
    def test_returns_text_response_with_images(self, mock_bedrock):
        body_payload = {"content": [{"text": "I see a diagram showing..."}]}
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(body_payload).encode()),
        }

        images = [
            {"media_type": "image/png", "data": "iVBORw0KGgoAAAANS..."},
            {"media_type": "image/jpeg", "data": "/9j/4AAQSkZJRg..."},
        ]
        result = bedrock_client.invoke_claude_multimodal("Describe these images", images)

        assert result == "I see a diagram showing..."
        mock_bedrock.invoke_model.assert_called_once()

        # Verify the request body structure
        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        request_body = json.loads(call_kwargs["body"])
        content_blocks = request_body["messages"][0]["content"]

        # Should have 2 image blocks + 1 text block
        assert len(content_blocks) == 3
        assert content_blocks[0]["type"] == "image"
        assert content_blocks[0]["source"]["type"] == "base64"
        assert content_blocks[0]["source"]["media_type"] == "image/png"
        assert content_blocks[0]["source"]["data"] == "iVBORw0KGgoAAAANS..."
        assert content_blocks[1]["type"] == "image"
        assert content_blocks[1]["source"]["media_type"] == "image/jpeg"
        assert content_blocks[2]["type"] == "text"
        assert content_blocks[2]["text"] == "Describe these images"

    def test_works_with_empty_images_list(self, mock_bedrock):
        body_payload = {"content": [{"text": "No images provided"}]}
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(body_payload).encode()),
        }

        result = bedrock_client.invoke_claude_multimodal("Hello", [])

        assert result == "No images provided"
        # Verify only text block is present
        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        request_body = json.loads(call_kwargs["body"])
        content_blocks = request_body["messages"][0]["content"]
        assert len(content_blocks) == 1
        assert content_blocks[0]["type"] == "text"

    def test_retries_on_throttling(self, mock_bedrock):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        success_body = {"content": [{"text": "OK"}]}
        mock_bedrock.invoke_model.side_effect = [
            throttle_error,
            {"body": io.BytesIO(json.dumps(success_body).encode())},
        ]

        images = [{"media_type": "image/png", "data": "abc123"}]
        with patch("src.utils.bedrock_client.time.sleep"):
            result = bedrock_client.invoke_claude_multimodal("test", images)

        assert result == "OK"
        assert mock_bedrock.invoke_model.call_count == 2

    def test_raises_after_max_retries(self, mock_bedrock):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "InvokeModel",
        )
        mock_bedrock.invoke_model.side_effect = [throttle_error] * 3

        images = [{"media_type": "image/png", "data": "abc123"}]
        with patch("src.utils.bedrock_client.time.sleep"):
            with pytest.raises(ClientError):
                bedrock_client.invoke_claude_multimodal("test", images)

        assert mock_bedrock.invoke_model.call_count == 3

    def test_uses_custom_max_tokens_and_temperature(self, mock_bedrock):
        body_payload = {"content": [{"text": "response"}]}
        mock_bedrock.invoke_model.return_value = {
            "body": io.BytesIO(json.dumps(body_payload).encode()),
        }

        bedrock_client.invoke_claude_multimodal(
            "test", [], max_tokens=8192, temperature=0.7
        )

        call_kwargs = mock_bedrock.invoke_model.call_args[1]
        request_body = json.loads(call_kwargs["body"])
        assert request_body["max_tokens"] == 8192
        assert request_body["temperature"] == 0.7
