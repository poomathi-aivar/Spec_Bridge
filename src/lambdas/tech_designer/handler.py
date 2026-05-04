"""Tech Designer Lambda handler.

Generates REST API endpoint definitions (OpenAPI 3.0), PostgreSQL DDL schemas,
and workflow definitions (Mermaid syntax) from extracted requirements.
For multi-document Projects, queries the Bedrock Knowledge Base for context.

Requirements: 4.1–4.16
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.models.data_models import Workflow, WorkflowStep
from src.utils import bedrock_client, kb_client

logger = logging.getLogger(__name__)

# Maximum retries for Bedrock invocations (handled by bedrock_client internally,
# but we add application-level retry for JSON parse failures)
MAX_PARSE_RETRIES = 3


# ---------------------------------------------------------------------------
# KB Context Retrieval
# ---------------------------------------------------------------------------


def _retrieve_kb_context(knowledge_base_id: str, query: str) -> str:
    """Query the Knowledge Base and return concatenated context text."""
    results = kb_client.retrieve(
        knowledge_base_id=knowledge_base_id,
        query_text=query,
        num_results=15,
    )
    chunks = [r.get("text", "") for r in results if r.get("text")]
    return "\n\n---\n\n".join(chunks)


# ---------------------------------------------------------------------------
# Requirement Helpers
# ---------------------------------------------------------------------------


def _format_requirements_for_prompt(requirements: list[dict[str, Any]]) -> str:
    """Format requirements into a readable text block for the prompt."""
    parts: list[str] = []
    for req in requirements:
        categories = ", ".join(req.get("categories", []))
        parts.append(
            f"[{req.get('requirement_id', 'N/A')}] ({categories}) "
            f"{req.get('title', '')}\n"
            f"  Description: {req.get('description', '')}"
        )
    return "\n\n".join(parts)


def _get_requirements_by_category(
    requirements: list[dict[str, Any]], category: str
) -> list[dict[str, Any]]:
    """Filter requirements by a specific category."""
    return [
        req for req in requirements
        if category in req.get("categories", [])
    ]


# ---------------------------------------------------------------------------
# Prompt Construction
# ---------------------------------------------------------------------------


def _build_api_design_prompt(
    requirements_text: str,
    kb_context: str | None,
) -> str:
    """Build the prompt for API design generation."""
    context_section = ""
    if kb_context:
        context_section = (
            f"ADDITIONAL PROJECT CONTEXT (from knowledge base):\n"
            f"{kb_context}\n\n"
        )

    return f"""{context_section}You are a senior API architect. Based on the following business requirements, generate a complete REST API specification in OpenAPI 3.0 format.

REQUIREMENTS:
{requirements_text}

INSTRUCTIONS:
1. Generate REST API endpoint definitions for each functional and integration requirement.
2. For each endpoint, include: HTTP method, path, description, request body JSON Schema, response body JSON Schema, HTTP status codes (at least one success and one error), and error response schemas.
3. Group endpoints by resource or domain area using tags.
4. Use proper OpenAPI 3.0 structure with info, paths, components/schemas sections.
5. Include common error schemas (400, 401, 404, 500) in components.

Return your response as a valid JSON object representing an OpenAPI 3.0 specification. The JSON must include:
- "openapi": "3.0.0"
- "info" with title and version
- "paths" with endpoint definitions
- "components" with "schemas" for request/response bodies

Return ONLY valid JSON. Do not include any text before or after the JSON object."""


def _build_schema_design_prompt(
    requirements_text: str,
    kb_context: str | None,
) -> str:
    """Build the prompt for database schema design generation."""
    context_section = ""
    if kb_context:
        context_section = (
            f"ADDITIONAL PROJECT CONTEXT (from knowledge base):\n"
            f"{kb_context}\n\n"
        )

    return f"""{context_section}You are a senior database architect. Based on the following business requirements, generate a PostgreSQL database schema.

REQUIREMENTS:
{requirements_text}

INSTRUCTIONS:
1. Generate CREATE TABLE statements with appropriate column names, data types, and constraints (NOT NULL, UNIQUE, CHECK, DEFAULT).
2. Define primary keys for every table.
3. Define foreign key relationships between tables where appropriate.
4. Suggest indexes based on anticipated query patterns derived from the requirements.
5. Include an entity-relationship description explaining how the tables relate to each other.

Return your response as a JSON object with this exact structure:
{{
  "ddl_statements": "CREATE TABLE ... ; CREATE INDEX ... ;",
  "er_description": "A textual description of entity relationships and how tables connect."
}}

The "ddl_statements" field must contain valid PostgreSQL DDL as a single string with statements separated by semicolons.
The "er_description" field must be a non-empty string describing the entity relationships.

Return ONLY valid JSON. Do not include any text before or after the JSON object."""


def _build_workflow_design_prompt(
    requirements_text: str,
    kb_context: str | None,
) -> str:
    """Build the prompt for workflow design generation."""
    context_section = ""
    if kb_context:
        context_section = (
            f"ADDITIONAL PROJECT CONTEXT (from knowledge base):\n"
            f"{kb_context}\n\n"
        )

    return f"""{context_section}You are a senior systems architect specializing in workflow design. Based on the following business requirements, generate workflow definitions.

REQUIREMENTS:
{requirements_text}

INSTRUCTIONS:
1. Identify processes or sequences described in the requirements and generate workflow definitions.
2. Each workflow must include: steps, decision points, transitions between steps, and error/exception paths.
3. Identify the actor or system component responsible for each step.
4. Output each workflow in Mermaid flowchart syntax.
5. Link each workflow back to the originating requirement IDs.
6. Include at least one error/exception path per workflow.

Return your response as a JSON object with this exact structure:
{{
  "workflows": [
    {{
      "workflow_id": "WF-001",
      "title": "Descriptive workflow title",
      "requirement_ids": ["REQ-001", "REQ-002"],
      "steps": [
        {{
          "step_id": "STEP-001",
          "description": "Step description",
          "actor": "Actor or component name",
          "step_type": "action|decision|error|start|end",
          "transitions": ["STEP-002"]
        }}
      ],
      "mermaid_syntax": "graph TD\\n    A[Start] --> B{{Decision}}\\n    B -->|Yes| C[Action]\\n    B -->|No| D[Error Handler]\\n    C --> E[End]\\n    D --> E"
    }}
  ]
}}

Each workflow MUST have:
- At least one step with a non-empty actor
- At least one error/exception path (a step with step_type "error")
- Valid Mermaid flowchart syntax
- Non-empty requirement_ids linking back to source requirements

Return ONLY valid JSON. Do not include any text before or after the JSON object."""


# ---------------------------------------------------------------------------
# Response Parsing
# ---------------------------------------------------------------------------


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences from a response if present."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        text = text[first_newline + 1:]
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text


def _parse_openapi_response(response_text: str) -> dict[str, Any]:
    """Parse and validate the OpenAPI specification response.

    Validates that the response contains required OpenAPI 3.0 structure.
    """
    text = _strip_code_fences(response_text)
    spec = json.loads(text)

    # Validate basic OpenAPI structure
    if not isinstance(spec, dict):
        raise ValueError("OpenAPI response is not a JSON object")
    if "openapi" not in spec:
        spec["openapi"] = "3.0.0"
    if "info" not in spec:
        spec["info"] = {"title": "Generated API", "version": "1.0.0"}
    if "paths" not in spec:
        raise ValueError("OpenAPI response missing 'paths' field")

    return spec


def _parse_schema_response(response_text: str) -> tuple[str, str]:
    """Parse the schema design response.

    Returns (ddl_statements, er_description).
    """
    text = _strip_code_fences(response_text)
    data = json.loads(text)

    ddl_statements = data.get("ddl_statements", "")
    er_description = data.get("er_description", "")

    if not ddl_statements:
        raise ValueError("Schema response missing 'ddl_statements'")
    if not er_description:
        raise ValueError("Schema response missing 'er_description'")

    return ddl_statements, er_description


def _parse_workflow_response(response_text: str) -> list[Workflow]:
    """Parse the workflow design response into Workflow data model instances."""
    text = _strip_code_fences(response_text)
    data = json.loads(text)

    workflows: list[Workflow] = []
    for wf_data in data.get("workflows", []):
        steps = [
            WorkflowStep(
                step_id=step.get("step_id", ""),
                description=step.get("description", ""),
                actor=step.get("actor", ""),
                step_type=step.get("step_type", "action"),
                transitions=step.get("transitions", []),
            )
            for step in wf_data.get("steps", [])
        ]

        workflows.append(Workflow(
            workflow_id=wf_data.get("workflow_id", ""),
            title=wf_data.get("title", ""),
            requirement_ids=wf_data.get("requirement_ids", []),
            steps=steps,
            mermaid_syntax=wf_data.get("mermaid_syntax", ""),
        ))

    return workflows


# ---------------------------------------------------------------------------
# Bedrock Invocation with Retry
# ---------------------------------------------------------------------------


def _invoke_bedrock_with_parse_retry(
    prompt: str,
    parse_fn,
    stage_name: str,
):
    """Invoke Bedrock and retry up to MAX_PARSE_RETRIES on parse failures.

    The bedrock_client already handles transient AWS errors with retries.
    This adds application-level retry for cases where the model returns
    malformed JSON that fails to parse.
    """
    last_exception: Exception | None = None

    for attempt in range(MAX_PARSE_RETRIES):
        try:
            response_text = bedrock_client.invoke_claude(
                prompt=prompt,
                max_tokens=8192,
                temperature=0.2,
            )
            result = parse_fn(response_text)
            return result
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_exception = exc
            logger.warning(
                "%s: Parse attempt %d/%d failed: %s",
                stage_name, attempt + 1, MAX_PARSE_RETRIES, str(exc),
            )

    raise last_exception  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation Helpers
# ---------------------------------------------------------------------------


def _validate_openapi_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the OpenAPI spec structure.

    Ensures required fields are present and endpoints have proper structure.
    """
    # Ensure openapi version
    if "openapi" not in spec:
        spec["openapi"] = "3.0.0"

    # Ensure info section
    if "info" not in spec:
        spec["info"] = {"title": "Generated API", "version": "1.0.0"}
    elif "title" not in spec["info"]:
        spec["info"]["title"] = "Generated API"
    elif "version" not in spec["info"]:
        spec["info"]["version"] = "1.0.0"

    # Ensure paths exist
    if "paths" not in spec or not spec["paths"]:
        spec["paths"] = {}

    # Ensure components/schemas section exists
    if "components" not in spec:
        spec["components"] = {"schemas": {}}
    elif "schemas" not in spec["components"]:
        spec["components"]["schemas"] = {}

    return spec


def _validate_ddl(ddl_statements: str) -> str:
    """Validate DDL statements have basic structure.

    Checks that DDL contains at least one CREATE TABLE statement.
    """
    ddl_upper = ddl_statements.upper()
    if "CREATE TABLE" not in ddl_upper:
        raise ValueError("DDL must contain at least one CREATE TABLE statement")
    return ddl_statements


def _validate_workflows(workflows: list[Workflow]) -> list[Workflow]:
    """Validate workflow structure completeness.

    Ensures each workflow has steps, actors, and mermaid syntax.
    """
    for wf in workflows:
        if not wf.steps:
            logger.warning("Workflow %s has no steps", wf.workflow_id)
        if not wf.mermaid_syntax:
            logger.warning("Workflow %s has no mermaid_syntax", wf.workflow_id)
        if not wf.requirement_ids:
            logger.warning("Workflow %s has no requirement_ids", wf.workflow_id)

    return workflows


# ---------------------------------------------------------------------------
# Main Handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Tech Designer Lambda handler.

    Input:
        {
            "projectId": "string",
            "requirements": [ExtractedRequirement as dict, ...],
            "knowledgeBaseId": "string | null"
        }

    Output:
        {
            "projectId": "string",
            "openApiSpec": dict,          # OpenAPI 3.0 JSON
            "ddlStatements": str,         # PostgreSQL DDL
            "erDescription": str,         # Entity-relationship description
            "workflows": [Workflow as dict, ...]
        }
    """
    project_id = event["projectId"]
    requirements = event["requirements"]
    knowledge_base_id = event.get("knowledgeBaseId")

    logger.info(
        "Tech Designer processing project %s (%d requirements, KB=%s)",
        project_id,
        len(requirements),
        knowledge_base_id or "None (no KB)",
    )

    # Retrieve KB context for multi-document projects
    kb_context: str | None = None
    if knowledge_base_id:
        # Build a query from requirement titles and descriptions
        query_parts: list[str] = []
        for req in requirements[:10]:  # Limit to first 10 for query
            query_parts.append(
                f"{req.get('title', '')} {req.get('description', '')}"
            )
        query_text = " ".join(query_parts)[:2000]
        kb_context = _retrieve_kb_context(knowledge_base_id, query_text)
        logger.info("Retrieved KB context: %d characters", len(kb_context))

    # Format requirements for prompts
    requirements_text = _format_requirements_for_prompt(requirements)

    # --- API Design ---
    logger.info("Generating API design...")
    api_prompt = _build_api_design_prompt(requirements_text, kb_context)
    openapi_spec = _invoke_bedrock_with_parse_retry(
        prompt=api_prompt,
        parse_fn=_parse_openapi_response,
        stage_name="API Design",
    )
    openapi_spec = _validate_openapi_spec(openapi_spec)
    logger.info(
        "API design complete: %d paths",
        len(openapi_spec.get("paths", {})),
    )

    # --- Schema Design ---
    logger.info("Generating schema design...")
    schema_prompt = _build_schema_design_prompt(requirements_text, kb_context)
    ddl_statements, er_description = _invoke_bedrock_with_parse_retry(
        prompt=schema_prompt,
        parse_fn=_parse_schema_response,
        stage_name="Schema Design",
    )
    ddl_statements = _validate_ddl(ddl_statements)
    logger.info("Schema design complete: %d chars DDL", len(ddl_statements))

    # --- Workflow Design ---
    logger.info("Generating workflow design...")
    workflow_prompt = _build_workflow_design_prompt(requirements_text, kb_context)
    workflows = _invoke_bedrock_with_parse_retry(
        prompt=workflow_prompt,
        parse_fn=_parse_workflow_response,
        stage_name="Workflow Design",
    )
    workflows = _validate_workflows(workflows)
    logger.info("Workflow design complete: %d workflows", len(workflows))

    return {
        "projectId": project_id,
        "openApiSpec": openapi_spec,
        "ddlStatements": ddl_statements,
        "erDescription": er_description,
        "workflows": [wf.to_dict() for wf in workflows],
    }
