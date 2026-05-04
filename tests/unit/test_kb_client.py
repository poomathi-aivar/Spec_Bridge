"""Unit tests for src/utils/kb_client.py."""

from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from src.utils import kb_client


@pytest.fixture()
def mock_agent_client():
    with patch.object(kb_client, "_get_agent_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


@pytest.fixture()
def mock_runtime_client():
    with patch.object(kb_client, "_get_agent_runtime_client") as mock:
        client = MagicMock()
        mock.return_value = client
        yield client


class TestStartIngestionJob:
    def test_returns_ingestion_job_id(self, mock_agent_client):
        mock_agent_client.start_ingestion_job.return_value = {
            "ingestionJob": {"ingestionJobId": "ingest-123"}
        }

        result = kb_client.start_ingestion_job(
            knowledge_base_id="kb-1", data_source_id="ds-1"
        )

        assert result == "ingest-123"
        mock_agent_client.start_ingestion_job.assert_called_once_with(
            knowledgeBaseId="kb-1", dataSourceId="ds-1"
        )

    def test_uses_env_defaults(self, mock_agent_client):
        mock_agent_client.start_ingestion_job.return_value = {
            "ingestionJob": {"ingestionJobId": "ingest-456"}
        }

        with patch.object(kb_client, "BEDROCK_KB_ID", "env-kb"), \
             patch.object(kb_client, "BEDROCK_KB_DATA_SOURCE_ID", "env-ds"):
            result = kb_client.start_ingestion_job()

        assert result == "ingest-456"
        mock_agent_client.start_ingestion_job.assert_called_once_with(
            knowledgeBaseId="env-kb", dataSourceId="env-ds"
        )

    def test_retries_on_throttling(self, mock_agent_client):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "StartIngestionJob",
        )
        mock_agent_client.start_ingestion_job.side_effect = [
            throttle_error,
            {"ingestionJob": {"ingestionJobId": "ingest-789"}},
        ]

        with patch("src.utils.kb_client.time.sleep"):
            result = kb_client.start_ingestion_job(
                knowledge_base_id="kb-1", data_source_id="ds-1"
            )

        assert result == "ingest-789"
        assert mock_agent_client.start_ingestion_job.call_count == 2

    def test_raises_non_retryable_error(self, mock_agent_client):
        error = ClientError(
            {"Error": {"Code": "ResourceNotFoundException", "Message": "Not found"}},
            "StartIngestionJob",
        )
        mock_agent_client.start_ingestion_job.side_effect = error

        with pytest.raises(ClientError):
            kb_client.start_ingestion_job(
                knowledge_base_id="kb-1", data_source_id="ds-1"
            )


class TestGetIngestionJobStatus:
    def test_returns_status(self, mock_agent_client):
        mock_agent_client.get_ingestion_job.return_value = {
            "ingestionJob": {"status": "COMPLETE"}
        }

        result = kb_client.get_ingestion_job_status(
            knowledge_base_id="kb-1",
            ingestion_job_id="ingest-123",
            data_source_id="ds-1",
        )

        assert result == "COMPLETE"
        mock_agent_client.get_ingestion_job.assert_called_once_with(
            knowledgeBaseId="kb-1", dataSourceId="ds-1", ingestionJobId="ingest-123"
        )

    def test_retries_on_service_unavailable(self, mock_agent_client):
        error = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Unavailable"}},
            "GetIngestionJob",
        )
        mock_agent_client.get_ingestion_job.side_effect = [
            error,
            {"ingestionJob": {"status": "IN_PROGRESS"}},
        ]

        with patch("src.utils.kb_client.time.sleep"):
            result = kb_client.get_ingestion_job_status(
                knowledge_base_id="kb-1",
                ingestion_job_id="ingest-123",
                data_source_id="ds-1",
            )

        assert result == "IN_PROGRESS"
        assert mock_agent_client.get_ingestion_job.call_count == 2


class TestPollIngestionUntilComplete:
    def test_returns_complete_status(self, mock_agent_client):
        mock_agent_client.get_ingestion_job.side_effect = [
            {"ingestionJob": {"status": "IN_PROGRESS"}},
            {"ingestionJob": {"status": "IN_PROGRESS"}},
            {"ingestionJob": {"status": "COMPLETE"}},
        ]

        with patch("src.utils.kb_client.time.sleep"):
            result = kb_client.poll_ingestion_until_complete(
                knowledge_base_id="kb-1",
                ingestion_job_id="ingest-123",
                data_source_id="ds-1",
                timeout_seconds=60,
            )

        assert result == "COMPLETE"

    def test_returns_failed_status(self, mock_agent_client):
        mock_agent_client.get_ingestion_job.return_value = {
            "ingestionJob": {"status": "FAILED"}
        }

        with patch("src.utils.kb_client.time.sleep"):
            result = kb_client.poll_ingestion_until_complete(
                knowledge_base_id="kb-1",
                ingestion_job_id="ingest-123",
                data_source_id="ds-1",
            )

        assert result == "FAILED"

    def test_raises_timeout_error(self, mock_agent_client):
        mock_agent_client.get_ingestion_job.return_value = {
            "ingestionJob": {"status": "IN_PROGRESS"}
        }

        with patch("src.utils.kb_client.time.sleep"), \
             patch("src.utils.kb_client.time.time") as mock_time:
            # Simulate time passing beyond timeout
            mock_time.side_effect = [0, 0, 301]

            with pytest.raises(TimeoutError, match="did not complete within"):
                kb_client.poll_ingestion_until_complete(
                    knowledge_base_id="kb-1",
                    ingestion_job_id="ingest-123",
                    data_source_id="ds-1",
                    timeout_seconds=300,
                )


class TestRetrieve:
    def test_returns_retrieval_results(self, mock_runtime_client):
        mock_runtime_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "First result text"},
                    "metadata": {"source": "doc1.pdf"},
                    "location": {"type": "S3", "s3Location": {"uri": "s3://bucket/doc1.pdf"}},
                    "score": 0.95,
                },
                {
                    "content": {"text": "Second result text"},
                    "metadata": {"source": "doc2.pdf"},
                    "location": {"type": "S3", "s3Location": {"uri": "s3://bucket/doc2.pdf"}},
                    "score": 0.82,
                },
            ]
        }

        result = kb_client.retrieve(
            knowledge_base_id="kb-1",
            query_text="What are the requirements?",
            num_results=5,
        )

        assert len(result) == 2
        assert result[0]["text"] == "First result text"
        assert result[0]["score"] == 0.95
        assert result[0]["metadata"] == {"source": "doc1.pdf"}
        assert result[1]["text"] == "Second result text"

        mock_runtime_client.retrieve.assert_called_once_with(
            knowledgeBaseId="kb-1",
            retrievalQuery={"text": "What are the requirements?"},
            retrievalConfiguration={
                "vectorSearchConfiguration": {"numberOfResults": 5}
            },
        )

    def test_returns_empty_list_when_no_results(self, mock_runtime_client):
        mock_runtime_client.retrieve.return_value = {"retrievalResults": []}

        result = kb_client.retrieve(
            knowledge_base_id="kb-1", query_text="obscure query"
        )

        assert result == []

    def test_retries_on_throttling(self, mock_runtime_client):
        throttle_error = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Retrieve",
        )
        mock_runtime_client.retrieve.side_effect = [
            throttle_error,
            {"retrievalResults": [{"content": {"text": "result"}, "metadata": {}, "location": {}, "score": 0.9}]},
        ]

        with patch("src.utils.kb_client.time.sleep"):
            result = kb_client.retrieve(
                knowledge_base_id="kb-1", query_text="test"
            )

        assert len(result) == 1
        assert mock_runtime_client.retrieve.call_count == 2

    def test_uses_default_num_results(self, mock_runtime_client):
        mock_runtime_client.retrieve.return_value = {"retrievalResults": []}

        kb_client.retrieve(knowledge_base_id="kb-1", query_text="test")

        call_kwargs = mock_runtime_client.retrieve.call_args[1]
        assert call_kwargs["retrievalConfiguration"]["vectorSearchConfiguration"]["numberOfResults"] == 10
