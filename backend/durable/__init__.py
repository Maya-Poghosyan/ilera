"""Azure Durable Functions pipeline for Ilera eligibility assessment.

This package contains the orchestrators, activities, and supporting tools that
implement the fan-out/fan-in eligibility workflow as a Durable Functions application.

Package layout:
  tools/         Pure Python helpers (gate functions, RAG tool factory).
  activities/    Azure Functions activity triggers (gate, specialist, synthesis).
  orchestrators/ Azure Functions orchestration triggers (eligibility, peer_query).
  errors.py      Structured error hierarchy (already written).
  models.py      Typed I/O contracts for all activities (already written).
  client.py      FastAPI → Durable HTTP bridge.
"""
