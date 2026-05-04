"""Architecture Advisor Lambda handler.

Recommends architecture patterns, identifies key components and interactions,
provides scalability/availability/security recommendations from NFRs,
recommends integration patterns, and includes rationale linked to requirement IDs.
For multi-document Projects, queries the Bedrock Knowledge Base for context.

Requirements: 5.1–5.6
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.models.data_models import (
    ArchitectureRecommendation,
    ComponentDescription,
    IntegrationPattern,
    RationaleEntry,
)
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


def _build_architecture_prompt(
    requirements_text: str,
    nfr_text: str,
    integration_text: str,
    kb_context: str | None,
) -> str:
    """Build the prompt for architecture recommendation generation."""
    context_section = ""
    if kb_context:
        context_section = (
            f"ADDITIONAL PROJECT CONTEXT (from knowledge base):\n"
            f"{kb_context}\n\n"
        )

    nfr_section = ""
    if nfr_text:
        nfr_section = (
            f"NON-FUNCTIONAL REQUIREMENTS:\n"
            f"{nfr_text}\n\n"
        )

    integration_section = ""
    if integration_text:
        integration_section = (
            f"INTEGRATION REQUIREMENTS:\n"
            f"{integration_text}\n\n"
        )

    return f"""{context_section}You are a senior solutions architect. Based on the following business requirements, provide comprehensive architecture recommendations.

ALL REQUIREMENTS:
{requirements_text}

{nfr_section}{integration_section}INSTRUCTIONS:
1. Recommend a system architecture pattern suitable for the identified requirements (e.g., microservices, monolith, serverless, event-driven, layered, hexagonal). Choose the pattern that best fits the requirements.
2. Identify key system components and describe the interactions between them. Each component should have a name, description, and list of interactions with other components.
3. Provide recommendations for scalability, availability, and security based on the non-functional requirements. If no NFRs are present, provide general best-practice recommendations.
4. Recommend integration patterns and protocols for external system interactions based on integration requirements. If no integration requirements are present, return an empty list.
5. Include a rationale for each architectural recommendation, linking it back to specific requirement IDs.

Return your response as a valid JSON object with this exact structure:
{{
  "pattern": "The recommended architecture pattern name (e.g., microservices, serverless, monolith)",
  "components": [
    {{
      "name": "Component Name",
      "description": "What this component does",
      "interactions": ["Interacts with Component B via REST API", "Publishes events to Message Queue"]
    }}
  ],
  "scalability_notes": "Recommendations for horizontal/vertical scaling, caching, load balancing, etc.",
  "availability_notes": "Recommendations for redundancy, failover, health checks, etc.",
  "security_notes": "Recommendations for authentication, authorization, encryption, etc.",
  "integration_patterns": [
    {{
      "pattern": "Pattern name (e.g., API Gateway, Message Queue, Event Bus)",
      "protocol": "Protocol (e.g., REST, gRPC, AMQP, WebSocket)",
      "description": "How this pattern addresses the integration requirement",
      "requirement_ids": ["REQ-001"]
    }}
  ],
  "rationale": [
    {{
      "recommendation": "Brief description of the recommendation",
      "requirement_ids": ["REQ-001", "REQ-002"],
      "justification": "Why this recommendation is appropriate given the requirements"
    }}
  ]
}}

IMPORTANT:
- The "pattern" field must be a non-empty string.
- The "components" array must contain at least one component with non-empty interactions.
- Every entry in "rationale" must reference at least one requirement ID.
- "scalability_notes", "availability_notes", and "security_notes" must be non-empty strings.
- If integration requirements are present, "integration_patterns" must contain at least one entry.

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


def _parse_architecture_response(response_text: str) -> ArchitectureRecommendation:
    """Parse and validate the architecture recommendation response."""
    text = _strip_code_fences(response_text)
    data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError("Architecture response is not a JSON object")

    pattern = data.get("pattern", "")
    if not pattern:
        raise ValueError("Architecture response missing 'pattern' field")

    components_data = data.get("components", [])
    if not components_data:
        raise ValueError("Architecture response missing 'components' field")

    components = [
        ComponentDescription(
            name=c.get("name", ""),
            description=c.get("description", ""),
            interactions=c.get("interactions", []),
        )
        for c in components_data
    ]

    scalability_notes = data.get("scalability_notes", "")
    if not scalability_notes:
        raise ValueError("Architecture response missing 'scalability_notes'")

    availability_notes = data.get("availability_notes", "")
    if not availability_notes:
        raise ValueError("Architecture response missing 'availability_notes'")

    security_notes = data.get("security_notes", "")
    if not security_notes:
        raise ValueError("Architecture response missing 'security_notes'")

    integration_patterns = [
        IntegrationPattern(
            pattern=ip.get("pattern", ""),
            protocol=ip.get("protocol", ""),
            description=ip.get("description", ""),
            requirement_ids=ip.get("requirement_ids", []),
        )
        for ip in data.get("integration_patterns", [])
    ]

    rationale = [
        RationaleEntry(
            recommendation=r.get("recommendation", ""),
            requirement_ids=r.get("requirement_ids", []),
            justification=r.get("justification", ""),
        )
        for r in data.get("rationale", [])
    ]

    return ArchitectureRecommendation(
        pattern=pattern,
        components=components,
        scalability_notes=scalability_notes,
        availability_notes=availability_notes,
        security_notes=security_notes,
        integration_patterns=integration_patterns,
        rationale=rationale,
    )


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


def _validate_architecture_recommendation(
    recommendation: ArchitectureRecommendation,
    has_integration_requirements: bool,
) -> ArchitectureRecommendation:
    """Validate the architecture recommendation structure.

    Ensures required fields are present and properly populated.
    """
    if not recommendation.pattern:
        logger.warning("Architecture recommendation has empty pattern")

    if not recommendation.components:
        logger.warning("Architecture recommendation has no components")

    for component in recommendation.components:
        if not component.name:
            logger.warning("Component has empty name")
        if not component.interactions:
            logger.warning("Component %s has no interactions", component.name)

    if not recommendation.rationale:
        logger.warning("Architecture recommendation has no rationale entries")

    for entry in recommendation.rationale:
        if not entry.requirement_ids:
            logger.warning(
                "Rationale entry '%s' has no requirement_ids",
                entry.recommendation,
            )

    if has_integration_requirements and not recommendation.integration_patterns:
        logger.warning(
            "Integration requirements present but no integration patterns recommended"
        )

    return recommendation


# ---------------------------------------------------------------------------
# Main Handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Architecture Advisor Lambda handler.

    Input:
        {
            "projectId": "string",
            "requirements": [ExtractedRequirement as dict, ...],
            "knowledgeBaseId": "string | null"
        }

    Output:
        {
            "projectId": "string",
            "architectureRecommendation": ArchitectureRecommendation as dict
        }
    """
    project_id = event["projectId"]
    requirements = event["requirements"]
    knowledge_base_id = event.get("knowledgeBaseId")

    logger.info(
        "Architecture Advisor processing project %s (%d requirements, KB=%s)",
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

    # Format requirements for prompt
    requirements_text = _format_requirements_for_prompt(requirements)

    # Extract NFR and integration requirements for focused sections
    nfr_requirements = _get_requirements_by_category(requirements, "non-functional")
    integration_requirements = _get_requirements_by_category(requirements, "integration")

    nfr_text = _format_requirements_for_prompt(nfr_requirements) if nfr_requirements else ""
    integration_text = _format_requirements_for_prompt(integration_requirements) if integration_requirements else ""

    # --- Architecture Recommendation ---
    logger.info("Generating architecture recommendation...")
    prompt = _build_architecture_prompt(
        requirements_text=requirements_text,
        nfr_text=nfr_text,
        integration_text=integration_text,
        kb_context=kb_context,
    )

    recommendation = _invoke_bedrock_with_parse_retry(
        prompt=prompt,
        parse_fn=_parse_architecture_response,
        stage_name="Architecture Advisor",
    )

    has_integration = len(integration_requirements) > 0
    recommendation = _validate_architecture_recommendation(recommendation, has_integration)

    logger.info(
        "Architecture recommendation complete: pattern=%s, %d components, %d rationale entries",
        recommendation.pattern,
        len(recommendation.components),
        len(recommendation.rationale),
    )

    return {
        "projectId": project_id,
        "architectureRecommendation": recommendation.to_dict(),
    }
