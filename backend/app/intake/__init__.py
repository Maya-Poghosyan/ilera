"""Schema-driven intake: question schema + answer→CaseProfile mapping."""

from .schema import INTAKE_SCHEMA, build_schema
from .mapping import map_answers_to_profile

__all__ = ["INTAKE_SCHEMA", "build_schema", "map_answers_to_profile"]
