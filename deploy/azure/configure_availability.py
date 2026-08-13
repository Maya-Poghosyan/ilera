#!/usr/bin/env python3
"""Give a container app HTTP health probes and a warm replica.

Why this exists: by default Azure probes the ingress port over TCP, which a process that is
listening but broken still passes, and it scales to zero, so a cold or crash-looping revision
answers visitors with Azure's "Container App - Unavailable" page. Probing /healthz and /readyz
over HTTP means a revision that can't serve never takes traffic, and the last good one keeps
answering instead.

Probes can only be set through `--yaml`, which replaces the whole definition, so this reads the
app's current configuration and edits it rather than writing one from scratch — env vars,
ingress and registry settings are carried over untouched. Secret *values* are re-read explicitly
(`az containerapp show` returns names only, and submitting those back would blank them), so this
needs permission to read them and writes them to a private temp file for the length of one az
call.

Run it with --dry-run first: it prints the definition it would submit and changes nothing.

Usage:
    export RESOURCE_GROUP=<your resource group>
    deploy/azure/configure_availability.py ilera-api --readiness-path /readyz
    deploy/azure/configure_availability.py ilera-web
    # add --dry-run to print what would change and apply nothing
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any


def az(*args: str) -> str:
    proc = subprocess.run(("az", *args), capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"az {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


# Everything else `show` returns — provisioningState, latestRevisionName, outboundIpAddresses,
# systemData and friends — is server-owned and rejected or ignored on the way back in.
WRITABLE_TOP_LEVEL = ("location", "tags", "identity", "properties")
WRITABLE_PROPERTIES = (
    "environmentId",
    "managedEnvironmentId",
    "workloadProfileName",
    "configuration",
    "template",
)


def strip_read_only(app: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in app.items() if k in WRITABLE_TOP_LEVEL}
    props = out.get("properties", {})
    out["properties"] = {k: v for k, v in props.items() if k in WRITABLE_PROPERTIES}
    ingress = out["properties"].get("configuration", {}).get("ingress")
    if ingress:
        ingress.pop("fqdn", None)
    return out


def restore_secret_values(app: dict[str, Any], name: str, resource_group: str) -> None:
    """Put the secret values back, or this update would replace them with empty strings."""
    config = app["properties"].get("configuration", {})
    secrets = config.get("secrets")
    if not secrets:
        return
    revealed = {
        s["name"]: s
        for s in json.loads(
            az("containerapp", "secret", "list", "-n", name, "-g", resource_group, "--show-values", "-o", "json")
        )
    }
    for secret in secrets:
        current = revealed.get(secret["name"], {})
        # Key Vault-backed secrets carry a reference instead of a value; leave those as they are.
        if "keyVaultUrl" in current:
            secret.update(current)
        elif "value" in current:
            secret["value"] = current["value"]
        else:
            sys.exit(
                f"couldn't read the value of secret {secret['name']!r}; aborting rather than "
                "submitting an update that would blank it"
            )


def probes(liveness_path: str, readiness_path: str | None, port: int) -> list[dict[str, Any]]:
    """Startup and liveness use the cheap endpoint; readiness may check dependencies.

    Thresholds are deliberately lenient on liveness (a slow reply shouldn't restart a working
    replica) and strict on readiness (traffic should leave a replica that can't serve quickly).
    """
    spec: list[dict[str, Any]] = [
        {
            "type": "Startup",
            "httpGet": {"path": liveness_path, "port": port},
            "initialDelaySeconds": 5,
            "periodSeconds": 3,
            "timeoutSeconds": 3,
            # 40 x 3s: generous, because a first boot applies the Postgres schema.
            "failureThreshold": 40,
        },
        {
            "type": "Liveness",
            "httpGet": {"path": liveness_path, "port": port},
            "initialDelaySeconds": 10,
            "periodSeconds": 20,
            "timeoutSeconds": 5,
            "failureThreshold": 3,
        },
    ]
    if readiness_path:
        spec.append(
            {
                "type": "Readiness",
                "httpGet": {"path": readiness_path, "port": port},
                "initialDelaySeconds": 5,
                "periodSeconds": 10,
                "timeoutSeconds": 5,
                "failureThreshold": 3,
            }
        )
    return spec


def patch(app: dict[str, Any], liveness_path: str, readiness_path: str | None) -> dict[str, Any]:
    template = app.setdefault("properties", {}).setdefault("template", {})
    containers = template.get("containers") or []
    if not containers:
        sys.exit("this app has no containers; is the name right?")

    ingress = app["properties"].get("configuration", {}).get("ingress") or {}
    port = ingress.get("targetPort")
    if not port:
        sys.exit("no ingress target port, so there is nothing to probe over HTTP")

    # Only the app container: sidecars have their own endpoints, and Azure allows one probe of
    # each type per container.
    containers[0]["probes"] = probes(liveness_path, readiness_path, port)

    scale = template.setdefault("scale", {})
    # Keeping one replica warm is what stops a cold start from looking like an outage.
    scale["minReplicas"] = max(1, scale.get("minReplicas") or 0)
    scale.setdefault("maxReplicas", max(2, scale.get("maxReplicas") or 0))
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="container app name, e.g. ilera-api")
    parser.add_argument("--resource-group", default=os.environ.get("RESOURCE_GROUP"))
    parser.add_argument("--liveness-path", default="/healthz")
    parser.add_argument(
        "--readiness-path",
        default=None,
        help="endpoint that fails while dependencies are unusable (the API's /readyz)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.resource_group:
        sys.exit("set RESOURCE_GROUP or pass --resource-group")

    current = json.loads(az("containerapp", "show", "-n", args.app, "-g", args.resource_group, "-o", "json"))
    updated = patch(strip_read_only(current), args.liveness_path, args.readiness_path)

    if args.dry_run:
        print(json.dumps(updated, indent=2))
        return

    restore_secret_values(updated, args.app, args.resource_group)

    # --yaml accepts JSON, which is a subset of YAML, so no yaml dependency is needed. The file
    # holds secret values, so it is created 0600 by mkstemp and removed straight after.
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(updated, fh)
        az("containerapp", "update", "-n", args.app, "-g", args.resource_group, "--yaml", path)
    finally:
        os.unlink(path)
    print(f"{args.app}: probes set, minReplicas >= 1")


if __name__ == "__main__":
    main()
