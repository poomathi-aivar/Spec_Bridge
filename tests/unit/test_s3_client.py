"""Unit tests for src/utils/s3_client.py."""

import io
from unittest.mock import MagicMock, patch

import pytest

from src.utils import s3_client


@pytest.fixture()
def mock_s3():
    with patch.object(s3_client, "_get_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestUploadFile:
    def test_uploads_with_sse_kms(self, mock_s3):
        key = s3_client.upload_file("uploads/doc1/original.pdf", b"data")

        assert key == "uploads/doc1/original.pdf"
        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ServerSideEncryption"] == "aws:kms"

    @patch.dict("os.environ", {"S3_SSE_TYPE": "AES256"})
    def test_uploads_with_sse_s3(self, mock_s3):
        # Re-import to pick up env change
        import importlib
        importlib.reload(s3_client)
        with patch.object(s3_client, "_get_client", return_value=mock_s3):
            s3_client.upload_file("key", b"data")
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["ServerSideEncryption"] == "AES256"
        # Restore
        importlib.reload(s3_client)


class TestDownloadFile:
    def test_returns_bytes(self, mock_s3):
        body_mock = MagicMock()
        body_mock.read.return_value = b"file content"
        mock_s3.get_object.return_value = {"Body": body_mock}

        result = s3_client.download_file("uploads/doc1/original.pdf")

        assert result == b"file content"


class TestGeneratePresignedUrl:
    def test_returns_url(self, mock_s3):
        mock_s3.generate_presigned_url.return_value = "https://s3.example.com/signed"

        url = s3_client.generate_presigned_url("outputs/doc1/tech-spec.md")

        assert url == "https://s3.example.com/signed"
        mock_s3.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": s3_client.BUCKET_NAME, "Key": "outputs/doc1/tech-spec.md"},
            ExpiresIn=3600,
        )
