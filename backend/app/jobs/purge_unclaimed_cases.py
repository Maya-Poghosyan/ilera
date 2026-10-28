"""Drop cases whose intake was abandoned before anyone signed up.

Runs as the scheduled `ilera-purge-unclaimed` Container Apps Job (infra/azure/scanning/jobs.tf)
rather than a loop inside the API: every API replica would otherwise run its own sweep, and
each deploy restarted the loop's 24h timer, so with frequent deploys it rarely fired at all.
"""

from ..config import get_settings
from ..store import purge_unclaimed_cases

if __name__ == "__main__":
    try:
        deleted = purge_unclaimed_cases(get_settings().unclaimed_case_ttl_days)
    except Exception:
        print("unclaimed_case_purge_failed")
        raise SystemExit(1) from None
    print(f"purged={deleted}")
