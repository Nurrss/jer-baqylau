"""Create (or update the password of) the demo inspector in Supabase Auth via the Admin API.

    uv run --project apps/api python scripts/create_inspector.py
Uses SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DEMO_INSPECTOR_EMAIL/PASSWORD/NAME from .env.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401
import httpx


def main() -> int:
    from app.core.config import get_settings

    s = get_settings()
    key = s.supabase_service_role_key.get_secret_value()
    if not s.supabase_url or not key:
        print("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        return 1
    base = f"{s.supabase_url.rstrip('/')}/auth/v1/admin/users"
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    payload = {
        "email": s.demo_inspector_email,
        "password": s.demo_inspector_password.get_secret_value(),
        "email_confirm": True,
        "user_metadata": {"full_name": s.demo_inspector_name, "role": "inspector"},
    }
    with httpx.Client(timeout=30) as http:
        resp = http.post(base, json=payload, headers=headers)
        if resp.status_code in (200, 201):
            print(f"Inspector created: {s.demo_inspector_email}")
            return 0
        if resp.status_code == 422 or "already" in resp.text:
            users = http.get(base, params={"per_page": 1000}, headers=headers).json().get("users", [])
            user = next((u for u in users if u.get("email") == s.demo_inspector_email.lower()), None)
            if user is None:
                print(f"Unexpected response: {resp.status_code} {resp.text}")
                return 1
            upd = http.put(f"{base}/{user['id']}", json=payload, headers=headers)
            upd.raise_for_status()
            print(f"Inspector already existed, password/metadata updated: {s.demo_inspector_email}")
            return 0
        print(f"Failed: {resp.status_code} {resp.text}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
