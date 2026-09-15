"""Azure Durable Functions orchestrator implementations.

Orchestrators are GENERATOR functions (yield, never async/await) as required by the
Python Durable Functions SDK.  They coordinate activity fan-outs, sub-orchestrations,
and conditional re-runs without performing any I/O themselves.

  eligibility.py   Main orchestrator: gates → specialist fan-out → peer queries →
                   specialist re-runs → synthesis.
  peer_query.py    Sub-orchestrator: routes a cross-program question to the target
                   specialist and condenses the answer.
"""
