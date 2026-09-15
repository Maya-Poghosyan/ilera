"""Azure Durable Functions activity implementations.

Each module exposes exactly one async activity function registered via the shared
DFApp instance in function_app.py.  Activities in this pipeline never raise
exceptions (except synthesis when the DB write fails — that IS retryable): instead
they return structured result dicts with an error_record field set on failure.  This
design lets task_all fan-outs complete even when individual specialists degrade, and
keeps all failure context in the Durable execution history.
"""
