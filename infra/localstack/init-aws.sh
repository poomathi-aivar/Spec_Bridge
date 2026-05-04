#!/bin/bash
# =============================================================================
# LocalStack bootstrap — creates DynamoDB tables, S3 bucket, and Secrets Manager
# secret so the backend can run locally without a real AWS account.
#
# This script runs automatically when the localstack container starts.
# =============================================================================

set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ENDPOINT="http://localhost:4566"

echo "==> Creating S3 bucket..."
awslocal s3 mb "s3://spec-bridge-documents" --region "$REGION" 2>/dev/null || true

echo "==> Creating DynamoDB tables..."

awslocal dynamodb create-table \
  --table-name spec-bridge-projects \
  --attribute-definitions AttributeName=project_id,AttributeType=S \
  --key-schema AttributeName=project_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$REGION" 2>/dev/null || true

awslocal dynamodb create-table \
  --table-name spec-bridge-jobs \
  --attribute-definitions \
    AttributeName=job_id,AttributeType=S \
    AttributeName=project_id,AttributeType=S \
  --key-schema AttributeName=job_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --global-secondary-indexes \
    '[{
      "IndexName": "project-id-index",
      "KeySchema": [{"AttributeName": "project_id", "KeyType": "HASH"}],
      "Projection": {"ProjectionType": "ALL"}
    }]' \
  --region "$REGION" 2>/dev/null || true

echo "==> Creating Secrets Manager secret..."
awslocal secretsmanager create-secret \
  --name "spec-bridge/credentials" \
  --secret-string '{"placeholder": "local-dev-credentials"}' \
  --region "$REGION" 2>/dev/null || true

echo "==> LocalStack init complete."
echo "    S3 bucket:       spec-bridge-documents"
echo "    DynamoDB tables: spec-bridge-projects, spec-bridge-jobs"
echo "    Secret:          spec-bridge/credentials"
