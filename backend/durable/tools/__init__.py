"""Shared tools used by Durable activity functions.

  eligibility_checks.py  Pure-Python gate functions — fast disqualification checks
                         that avoid spinning up an LLM for clearly ineligible programs.
  rag_tool.py            Factory that returns a pydantic-ai tool bound to a specific
                         program scope in the RAG index.
"""
