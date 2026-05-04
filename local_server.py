"""
SPEC BRIDGE — Local development server.

A lightweight FastAPI application that wraps the Lambda handlers so the full
pipeline can be exercised locally via Docker without deploying to AWS.

Routes mirror the API Gateway configuration in infra/template.yaml:
  POST /projects              → Upload Service
  GET  /projects/{id}/status  → Status API
  GET  /projects/{id}/download→ Status API
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spec-bridge-local")

app = FastAPI(
    title="SPEC BRIDGE — Local Dev Server",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_apigw_event(
    method: str,
    path: str,
    resource: str,
    path_params: dict[str, str] | None = None,
    query_params: dict[str, str] | None = None,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a minimal API Gateway proxy event dict."""
    return {
        "httpMethod": method,
        "path": path,
        "resource": resource,
        "pathParameters": path_params or {},
        "queryStringParameters": query_params or {},
        "headers": headers or {},
        "body": body,
    }


def _lambda_response_to_fastapi(result: dict[str, Any]) -> JSONResponse:
    """Convert a Lambda proxy response dict to a FastAPI JSONResponse."""
    status = result.get("statusCode", 200)
    body = result.get("body", "{}")
    headers = result.get("headers", {})
    # Remove CORS headers — FastAPI middleware handles them
    headers.pop("Access-Control-Allow-Origin", None)
    try:
        parsed = json.loads(body) if isinstance(body, str) else body
    except (json.JSONDecodeError, TypeError):
        parsed = {"raw": body}
    return JSONResponse(content=parsed, status_code=status, headers=headers)


# ---------------------------------------------------------------------------
# Helpers — project status mapping
# ---------------------------------------------------------------------------

def _map_status(raw: str) -> str:
    """Map DynamoDB status to frontend-expected values."""
    upper = (raw or "").upper()
    if upper in ("COMPLETED",):
        return "completed"
    if upper in ("FAILED",):
        return "failed"
    # CREATED, UPLOADED, PROCESSING, or anything else = processing
    return "processing"


# ---------------------------------------------------------------------------
# GET /projects — List all projects
# ---------------------------------------------------------------------------

@app.get("/projects")
async def list_projects():
    """List all projects from DynamoDB."""
    import decimal
    from src.utils import dynamodb_client

    class DecimalEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, decimal.Decimal):
                return int(o) if o == int(o) else float(o)
            return super().default(o)

    try:
        table = dynamodb_client._get_projects_table()
        response = table.scan()
        items = response.get("Items", [])
        items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        # Map to frontend-expected camelCase format
        projects = []
        for item in items:
            projects.append({
                "projectId": item.get("project_id", ""),
                "name": item.get("name", "Untitled Project"),
                "description": item.get("description"),
                "documentIds": item.get("document_ids", []),
                "status": _map_status(item.get("status", "")),
                "createdAt": item.get("created_at", ""),
            })
        serialized = json.loads(json.dumps(projects, cls=DecimalEncoder))
        return JSONResponse(content=serialized)
    except Exception as exc:
        logger.exception("Failed to list projects")
        return JSONResponse(
            content={"error": str(exc)},
            status_code=500,
        )


# ---------------------------------------------------------------------------
# POST /projects — Upload Service
# ---------------------------------------------------------------------------

@app.post("/projects")
async def create_project(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    """Proxy to the Upload Service Lambda handler.

    Converts FastAPI-parsed multipart files into the JSON multi-file format
    that the Lambda handler expects.
    """
    from src.lambdas.upload_service.handler import handler as upload_handler

    if not files:
        return JSONResponse(
            content={"error": "No files provided"},
            status_code=400,
        )

    # Build the multi-file JSON body the handler expects:
    # {"files": [{"filename": "...", "content": "<base64>"}, ...]}
    files_payload = []
    for f in files:
        content = await f.read()
        files_payload.append({
            "filename": f.filename or "unknown",
            "content": base64.b64encode(content).decode("utf-8"),
        })

    json_body = json.dumps({"files": files_payload, "name": name, "description": description})

    event = {
        "httpMethod": "POST",
        "path": "/projects",
        "resource": "/projects",
        "pathParameters": {},
        "queryStringParameters": {},
        "headers": dict(request.headers),
        "body": json_body,
        "isBase64Encoded": False,
    }

    result = upload_handler(event, None)
    return _lambda_response_to_fastapi(result)


# ---------------------------------------------------------------------------
# GET /projects/{projectId}/status — Status API
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/status")
async def get_status(project_id: str):
    """Proxy to the Status API Lambda handler."""
    from src.lambdas.status_api.handler import handler as status_handler

    event = _build_apigw_event(
        method="GET",
        path=f"/projects/{project_id}/status",
        resource="/projects/{projectId}/status",
        path_params={"projectId": project_id},
    )
    result = status_handler(event, None)
    return _lambda_response_to_fastapi(result)


# ---------------------------------------------------------------------------
# GET /projects/{projectId}/download — Status API
# ---------------------------------------------------------------------------

@app.get("/projects/{project_id}/download")
async def get_download(project_id: str, format: str = "md"):
    """Proxy to the Status API Lambda handler (download endpoint)."""
    from src.lambdas.status_api.handler import handler as status_handler

    event = _build_apigw_event(
        method="GET",
        path=f"/projects/{project_id}/download",
        resource="/projects/{projectId}/download",
        path_params={"projectId": project_id},
        query_params={"format": format},
    )
    result = status_handler(event, None)
    return _lambda_response_to_fastapi(result)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "spec-bridge-backend"}
