"""One-shot entrypoints run on a schedule by Container Apps Jobs, outside the API process.

Each module is runnable as `python -m app.jobs.<name>` from the API image and exits non-zero
on failure so the job execution shows as failed.
"""
