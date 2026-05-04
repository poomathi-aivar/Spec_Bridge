#!/bin/bash
# =============================================================================
# Deploy all SPEC BRIDGE Lambda functions to AWS
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - An IAM role for Lambda execution (see below)
#
# Usage:
#   1. Create a Lambda execution role in IAM first (see instructions below)
#   2. Set your values:
#        export AWS_REGION=ap-south-1
#        export LAMBDA_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT:role/spec-bridge-lambda-role
#   3. Run: bash scripts/deploy_lambdas.sh
# =============================================================================

set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
ROLE_ARN="${LAMBDA_ROLE_ARN:?Set LAMBDA_ROLE_ARN to your Lambda execution role ARN}"
RUNTIME="python3.12"
PACKAGE_DIR="$(mktemp -d)"
ZIP_FILE="${PACKAGE_DIR}/lambda-package.zip"

# Environment variables shared by all Lambdas
S3_BUCKET="${S3_BUCKET_NAME:-spec-bridge-documents}"
JOBS_TABLE="${DYNAMODB_JOBS_TABLE_NAME:-spec-bridge-jobs}"
PROJECTS_TABLE="${DYNAMODB_PROJECTS_TABLE_NAME:-spec-bridge-projects}"
MODEL_ID="${BEDROCK_CLAUDE_MODEL_ID:-anthropic.claude-3-5-sonnet-20241022-v2:0}"
KB_ID="${BEDROCK_KB_ID:-}"
KB_DS_ID="${BEDROCK_KB_DATA_SOURCE_ID:-}"
SECRET="${SECRET_NAME:-spec-bridge/credentials}"

echo "==> Packaging Lambda code..."
pip install -r requirements.txt -t "${PACKAGE_DIR}/pkg" --quiet
cp -r src/ "${PACKAGE_DIR}/pkg/src/"
(cd "${PACKAGE_DIR}/pkg" && zip -r "${ZIP_FILE}" . -q)
echo "    Package: ${ZIP_FILE} ($(du -h "${ZIP_FILE}" | cut -f1))"

# Common env vars JSON
ENV_VARS="{\"Variables\":{\"AWS_REGION\":\"${REGION}\",\"S3_BUCKET_NAME\":\"${S3_BUCKET}\",\"S3_SSE_TYPE\":\"AES256\",\"DYNAMODB_JOBS_TABLE_NAME\":\"${JOBS_TABLE}\",\"DYNAMODB_PROJECTS_TABLE_NAME\":\"${PROJECTS_TABLE}\",\"BEDROCK_CLAUDE_MODEL_ID\":\"${MODEL_ID}\",\"BEDROCK_KB_ID\":\"${KB_ID}\",\"BEDROCK_KB_DATA_SOURCE_ID\":\"${KB_DS_ID}\",\"SECRET_NAME\":\"${SECRET}\"}}"

create_or_update_lambda() {
    local NAME=$1
    local HANDLER=$2
    local TIMEOUT=$3
    local MEMORY=$4

    echo "==> Deploying ${NAME}..."

    # Check if function exists
    if aws lambda get-function --function-name "${NAME}" --region "${REGION}" > /dev/null 2>&1; then
        echo "    Updating existing function..."
        aws lambda update-function-code \
            --function-name "${NAME}" \
            --zip-file "fileb://${ZIP_FILE}" \
            --region "${REGION}" \
            --no-cli-pager > /dev/null

        # Wait for update to complete
        aws lambda wait function-updated --function-name "${NAME}" --region "${REGION}" 2>/dev/null || true

        aws lambda update-function-configuration \
            --function-name "${NAME}" \
            --handler "${HANDLER}" \
            --timeout "${TIMEOUT}" \
            --memory-size "${MEMORY}" \
            --environment "${ENV_VARS}" \
            --region "${REGION}" \
            --no-cli-pager > /dev/null
    else
        echo "    Creating new function..."
        aws lambda create-function \
            --function-name "${NAME}" \
            --runtime "${RUNTIME}" \
            --role "${ROLE_ARN}" \
            --handler "${HANDLER}" \
            --timeout "${TIMEOUT}" \
            --memory-size "${MEMORY}" \
            --zip-file "fileb://${ZIP_FILE}" \
            --environment "${ENV_VARS}" \
            --region "${REGION}" \
            --no-cli-pager > /dev/null
    fi

    # Get and print the ARN
    ARN=$(aws lambda get-function --function-name "${NAME}" --region "${REGION}" --query 'Configuration.FunctionArn' --output text)
    echo "    ✓ ${ARN}"
}

# Deploy all 7 Lambdas
create_or_update_lambda "spec-bridge-upload-service"         "src.lambdas.upload_service.handler.handler"         60  256
create_or_update_lambda "spec-bridge-document-processor"     "src.lambdas.document_processor.handler.handler"     900 1024
create_or_update_lambda "spec-bridge-requirement-extractor"  "src.lambdas.requirement_extractor.handler.handler"  900 1024
create_or_update_lambda "spec-bridge-tech-designer"          "src.lambdas.tech_designer.handler.handler"          900 1024
create_or_update_lambda "spec-bridge-architecture-advisor"   "src.lambdas.architecture_advisor.handler.handler"   900 1024
create_or_update_lambda "spec-bridge-tech-spec-assembler"    "src.lambdas.tech_spec_assembler.handler.handler"    300 1024
create_or_update_lambda "spec-bridge-status-api"             "src.lambdas.status_api.handler.handler"             30  256

echo ""
echo "==> All Lambdas deployed. Copy the ARNs above into your Step Functions definition."
echo ""
echo "==> Cleaning up..."
rm -rf "${PACKAGE_DIR}"
echo "    Done."
