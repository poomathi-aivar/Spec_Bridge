"""
Real token usage tester for Spec Bridge — Claude Sonnet 4.6.

Makes live AI Gateway calls using the actual prompt builders from each lambda
and reads token counts directly from the OpenAI-compatible response.

Run:
    python3 scripts/estimate_token_usage.py

Requirements:
    - AIGATEWAY_API_KEY environment variable set
    - openai package installed (pip install openai)
"""

from __future__ import annotations

import os
import sys
import time

import openai

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.lambdas.document_processor.handler import _build_summarization_prompt
from src.lambdas.requirement_extractor.handler import _build_extraction_prompt
from src.lambdas.architecture_advisor.handler import _build_architecture_prompt
from src.lambdas.tech_designer.handler import (
    _build_api_design_prompt,
    _build_schema_design_prompt,
    _build_workflow_design_prompt,
)

# ---------------------------------------------------------------------------
# Model config
# ---------------------------------------------------------------------------

AIGATEWAY_BASE_URL = os.environ.get("AIGATEWAY_BASE_URL", "https://aigateway.aivar.app")
AIGATEWAY_API_KEY  = os.environ.get("AIGATEWAY_API_KEY", "")
MODEL_ID           = os.environ.get("AIGATEWAY_MODEL", "claude-sonnet-4.6")

# ---------------------------------------------------------------------------
# Sample data — representative 10-requirement BRD project
# ---------------------------------------------------------------------------

SAMPLE_DOCUMENT_TEXT = """\
Executive Summary
This document describes the requirements for an e-commerce order management system.
The system shall allow customers to browse products, add items to a cart, place orders,
and track order status. The platform integrates with payment gateways, inventory systems,
and shipping providers.

1. User Authentication
Users must register with email and password. Sessions expire after 30 minutes of inactivity.
Password reset via email link is required. OAuth2 login with Google is optional.

2. Product Catalog
Display products with name, description, price, and availability. Pagination is required
(20 items per page). Search by name and category must be supported.

3. Shopping Cart
Authenticated users may add products to a cart. Cart persists across sessions.
Maximum 50 items per cart. Stock validation occurs at checkout.

4. Order Processing
Orders placed after checkout. Payment collected before order confirmation.
PENDING orders cancellable within 15 min. PROCESSING orders cannot be cancelled.

5. Payment Integration
Stripe is the primary payment processor. PayPal is secondary.
TLS 1.2+ required. PCI-DSS compliance mandatory.

6. Inventory Management
Inventory updated in real time on order placement. Low stock alert at 10 units.
Backorder support for select categories.

7. Shipping & Fulfillment
FedEx and UPS integrated for rate calculation. Tracking numbers emailed on shipment.
International shipping requires customs declaration.

8. Reporting & Analytics
Admins view daily/weekly/monthly sales reports. CSV export available.
Customer lifetime value and cohort analysis required.

9. Non-Functional Requirements
10,000 concurrent users. 99.9% uptime SLA. 200ms p95 response time.
AES-256 encryption at rest.

10. Integration Requirements
REST API for third-party integrations. Webhook support for order status events.
GraphQL endpoint is a future consideration.
""" * 2  # ~1000 words, simulating a typical BRD

SAMPLE_REQUIREMENTS = [
    {
        "requirement_id": "REQ-001",
        "title": "User Registration and Authentication",
        "description": "Users register with email/password. Sessions expire after 30 min inactivity. "
                       "Password reset via email. OAuth2 with Google optional.",
        "categories": ["functional", "security"],
    },
    {
        "requirement_id": "REQ-002",
        "title": "Product Catalog with Search and Pagination",
        "description": "Display products with name, description, price, availability. "
                       "20 items/page pagination. Search by name and category.",
        "categories": ["functional"],
    },
    {
        "requirement_id": "REQ-003",
        "title": "Shopping Cart Persistence",
        "description": "Authenticated users add products. Cart persists across sessions. "
                       "Max 50 items. Stock validation at checkout.",
        "categories": ["functional", "data"],
    },
    {
        "requirement_id": "REQ-004",
        "title": "Order Processing Workflow",
        "description": "Orders placed after checkout. Payment before confirmation. "
                       "PENDING cancellable within 15 min. PROCESSING non-cancellable.",
        "categories": ["functional"],
    },
    {
        "requirement_id": "REQ-005",
        "title": "Payment Gateway Integration",
        "description": "Stripe primary, PayPal secondary. TLS 1.2+ required. PCI-DSS compliance.",
        "categories": ["functional", "integration", "security"],
    },
    {
        "requirement_id": "REQ-006",
        "title": "Real-time Inventory Management",
        "description": "Inventory updated on order placement. Low stock alert at 10 units. "
                       "Backorder support for select categories.",
        "categories": ["functional", "data"],
    },
    {
        "requirement_id": "REQ-007",
        "title": "Shipping Integration with FedEx and UPS",
        "description": "Rate calculation via FedEx and UPS. Tracking numbers emailed. "
                       "International shipping with customs declaration.",
        "categories": ["functional", "integration"],
    },
    {
        "requirement_id": "REQ-008",
        "title": "Sales Reporting and Analytics",
        "description": "Daily/weekly/monthly reports for admins. CSV export. "
                       "Customer lifetime value and cohort analysis.",
        "categories": ["functional", "non-functional"],
    },
    {
        "requirement_id": "REQ-009",
        "title": "High Availability and Performance",
        "description": "10,000 concurrent users. 99.9% uptime. 200ms p95 response. AES-256 at rest.",
        "categories": ["non-functional"],
    },
    {
        "requirement_id": "REQ-010",
        "title": "REST API and Webhook Integration",
        "description": "REST API for third-party integrations. Webhooks for order status. "
                       "GraphQL future consideration.",
        "categories": ["integration"],
    },
]

SAMPLE_NFR = [r for r in SAMPLE_REQUIREMENTS if "non-functional" in r.get("categories", [])]
SAMPLE_INTEGRATION = [r for r in SAMPLE_REQUIREMENTS if "integration" in r.get("categories", [])]


# ---------------------------------------------------------------------------
# AI Gateway caller — reads real usage from response
# ---------------------------------------------------------------------------

def _get_gateway_client() -> openai.OpenAI:
    if not AIGATEWAY_API_KEY:
        raise RuntimeError("AIGATEWAY_API_KEY environment variable is not set.")
    return openai.OpenAI(api_key=AIGATEWAY_API_KEY, base_url=AIGATEWAY_BASE_URL)


def call_bedrock(prompt: str, max_tokens: int = 4096, call_label: str = "") -> dict:
    """Make a live AI Gateway call and return real token usage + timing."""
    client = _get_gateway_client()

    print(f"  → Calling AI Gateway: {call_label} ...", flush=True)
    t0 = time.time()
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.2,
    )
    elapsed = time.time() - t0

    usage = response.usage
    input_tokens  = usage.prompt_tokens     if usage else 0
    output_tokens = usage.completion_tokens if usage else 0

    print(f"     ✓ input={input_tokens:,}  output={output_tokens:,}  "
          f"total={input_tokens + output_tokens:,}  ({elapsed:.1f}s)")

    return {
        "call_label": call_label,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "latency_s": round(elapsed, 1),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_requirements(requirements: list[dict]) -> str:
    parts = []
    for req in requirements:
        cats = ", ".join(req.get("categories", []))
        parts.append(
            f"[{req['requirement_id']}] ({cats}) {req['title']}\n"
            f"  Description: {req['description']}"
        )
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Run all calls
# ---------------------------------------------------------------------------

def run_all_calls() -> list[dict]:
    results = []

    # 1. document_processor — summarization
    prompt = _build_summarization_prompt(SAMPLE_DOCUMENT_TEXT)
    results.append({
        "lambda": "document_processor",
        **call_bedrock(prompt, max_tokens=2048, call_label="summarization"),
    })

    # 2. requirement_extractor — extraction
    prompt = _build_extraction_prompt(
        context_text=SAMPLE_DOCUMENT_TEXT,
        summary_preamble=None,
        is_multi_doc=False,
    )
    results.append({
        "lambda": "requirement_extractor",
        **call_bedrock(prompt, max_tokens=8192, call_label="requirement extraction"),
    })

    # 3. architecture_advisor — architecture recommendation
    req_text = fmt_requirements(SAMPLE_REQUIREMENTS)
    nfr_text = fmt_requirements(SAMPLE_NFR)
    int_text = fmt_requirements(SAMPLE_INTEGRATION)
    prompt = _build_architecture_prompt(
        requirements_text=req_text,
        nfr_text=nfr_text,
        integration_text=int_text,
        kb_context=None,
    )
    results.append({
        "lambda": "architecture_advisor",
        **call_bedrock(prompt, max_tokens=8192, call_label="architecture recommendation"),
    })

    # 4. tech_designer — API design
    prompt = _build_api_design_prompt(requirements_text=req_text, kb_context=None)
    results.append({
        "lambda": "tech_designer",
        **call_bedrock(prompt, max_tokens=8192, call_label="API design (OpenAPI)"),
    })

    # 5. tech_designer — schema design
    prompt = _build_schema_design_prompt(requirements_text=req_text, kb_context=None)
    results.append({
        "lambda": "tech_designer",
        **call_bedrock(prompt, max_tokens=8192, call_label="Schema design (DDL)"),
    })

    # 6. tech_designer — workflow design
    prompt = _build_workflow_design_prompt(requirements_text=req_text, kb_context=None)
    results.append({
        "lambda": "tech_designer",
        **call_bedrock(prompt, max_tokens=8192, call_label="Workflow design (Mermaid)"),
    })

    return results


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(results: list[dict]) -> None:
    total_input = sum(r["input_tokens"] for r in results)
    total_output = sum(r["output_tokens"] for r in results)
    total_all = sum(r["total_tokens"] for r in results)
    avg_total = total_all // len(results)

    print("\n" + "=" * 80)
    print(f"  TOKEN USAGE REPORT — SPEC BRIDGE (Live AI Gateway Calls)")
    print(f"  Model: {MODEL_ID}  |  Gateway: {AIGATEWAY_BASE_URL}")
    print("=" * 80)
    print(f"\n{'Lambda':<25} {'Call':<32} {'Input':>7} {'Output':>7} {'Total':>7} {'Time':>6}")
    print("-" * 80)

    for r in results:
        print(
            f"{r['lambda']:<25} {r['call_label']:<32} "
            f"{r['input_tokens']:>7,} {r['output_tokens']:>7,} "
            f"{r['total_tokens']:>7,} {r['latency_s']:>5.1f}s"
        )

    print("-" * 80)
    print(
        f"{'TOTAL':<57} {total_input:>7,} {total_output:>7,} {total_all:>7,}"
    )
    print(f"\n  Average tokens per Bedrock call (across {len(results)} calls): {avg_total:,}")
    print(f"  Average tokens per full pipeline run:                         {total_all:,}")
    print("=" * 80 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\nSpec Bridge — Live Token Usage Test")
    print(f"Model  : {MODEL_ID}")
    print(f"Gateway: {AIGATEWAY_BASE_URL}")
    print(f"Making {6} live AI Gateway calls...\n")

    try:
        results = run_all_calls()
        print_report(results)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        print("\nMake sure:")
        print("  1. AIGATEWAY_API_KEY is set")
        print(f"  2. Gateway is reachable: {AIGATEWAY_BASE_URL}")
        print(f"     Model: {MODEL_ID}")
        sys.exit(1)
