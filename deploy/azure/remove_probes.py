#!/usr/bin/env python3
"""Clear the health probes from a container app.

Probes held traffic off `ilera-api` even though the process was healthy and listening on the
ingress port, so they are gone: Azure's default TCP check on the ingress port decides again.

Probes can only be changed through `--yaml`, which replaces the whole definition, so this reads
the app's current configuration and edits it rather than writing one from scratch — env vars,
ingress and registry settings are carried over untouched. Secret *values* are re-read explicitly
(`az containerapp show` returns names only, and submitting those back would blank them), so this
needs permission to read them and writes them to a private temp file for the length of one az
call.

Usage:
    export RESOURCE_GROUP=Ilera
    deploy/azure/remove_probes.py ilera-api
    # add --dry-run to print what would be submitted and apply nothing
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


def clear_probes(app: dict[str, Any]) -> dict[str, Any]:
    containers = app.setdefault("properties", {}).setdefault("template", {}).get("containers") or []
    if not containers:
        sys.exit("this app has no containers; is the name right?")
    # An empty list, not a missing key: omitting `probes` leaves the existing ones in place.
    for container in containers:
        container["probes"] = []
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", help="container app name, e.g. ilera-api")
    parser.add_argument("--resource-group", default=os.environ.get("RESOURCE_GROUP"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.resource_group:
        sys.exit("set RESOURCE_GROUP or pass --resource-group")

    current = json.loads(az("containerapp", "show", "-n", args.app, "-g", args.resource_group, "-o", "json"))
    updated = clear_probes(strip_read_only(current))

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
    print(f"{args.app}: probes removed")


if __name__ == "__main__":
    main()
