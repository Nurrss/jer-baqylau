"""End-to-end smoke test of the core cycle (spec §6) against a running API — local or production.

    uv run --project apps/api python scripts/e2e_smoke.py --base-url http://localhost:8000
    uv run --project apps/api python scripts/e2e_smoke.py --base-url https://<api-host> --chat-id <your tg id>

Flow: health → inspector login → citizen signal (simulated, as the bot would create it)
→ parcel OK→UNDER_CHECK + events → confirm → VIOLATION → IN_REMEDIATION → RESOLVED
→ (optional) application status change → subscribers pushed.

With --chat-id the Telegram notifications are really delivered to that chat.
The run changes demo data: execute `make demo-reset` before presenting.
Credentials/keys are read from .env (SERVICE_API_KEY, DEMO_INSPECTOR_*, SUPABASE_*) or flags.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import _bootstrap  # noqa: F401
import httpx

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def jpeg_with_gps(lat: float, lon: float) -> bytes:
    """A small JPEG whose EXIF GPS points at the parcel (stands in for a phone photo on site)."""
    import io

    from PIL import Image

    def dms(value: float) -> tuple[float, float, float]:
        d = int(value)
        m = int((value - d) * 60)
        return (float(d), float(m), round(((value - d) * 60 - m) * 60, 4))

    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: dms(lat), 3: "E", 4: dms(lon)}
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (110, 130, 90)).save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


class SmokeError(RuntimeError):
    pass


def step(title: str) -> None:
    print(f"{DIM}→{RESET} {title}", flush=True)


def ok(message: str) -> None:
    print(f"  {GREEN}✓{RESET} {message}", flush=True)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)
    ok(message)


class Smoke:
    def __init__(self, args: argparse.Namespace) -> None:
        from app.core.config import get_settings

        self.settings = get_settings()
        self.base = args.base_url.rstrip("/")
        self.api = f"{self.base}/api/v1"
        self.args = args
        # Short keep-alive: edge proxies drop idle connections, reusing one fails with "Server disconnected".
        self.http = httpx.Client(timeout=120, limits=httpx.Limits(keepalive_expiry=5))
        self.service_key = args.service_key or self.settings.service_api_key.get_secret_value()
        self.auth: dict[str, str] = {}

    def _json(self, resp: httpx.Response, expected: int = 200) -> Any:
        if resp.status_code != expected:
            raise SmokeError(
                f"{resp.request.method} {resp.request.url} → {resp.status_code}: {resp.text[:400]}"
            )
        return resp.json()

    def get(self, path: str, **params: Any) -> Any:
        return self._json(self.http.get(f"{self.api}{path}", params=params, headers=self.auth))

    def post(self, path: str, body: dict[str, Any], expected: int = 200, service: bool = False) -> Any:
        headers = {"X-Service-Key": self.service_key} if service else self.auth
        return self._json(self.http.post(f"{self.api}{path}", json=body, headers=headers), expected)

    # ── steps ──────────────────────────────────────────────────────────────
    def health(self) -> None:
        step("Health")
        body = self._json(self.http.get(f"{self.base}/health"))
        check(
            body["database"] is True,
            f"database ok (env={body['env']}, bot={body['bot']}, storage={body['storage']})",
        )

    def login(self) -> None:
        step("Inspector login")
        mode = self._json(self.http.get(f"{self.api}/auth/config"))["mode"]
        email = self.args.email or self.settings.demo_inspector_email
        password = self.args.password or self.settings.demo_inspector_password.get_secret_value()
        if mode == "local":
            token = self.post("/auth/login", {"email": email, "password": password})["access_token"]
        else:
            supabase_url = self.args.supabase_url or self.settings.supabase_url
            anon = self.args.supabase_anon_key or self.settings.supabase_anon_key.get_secret_value()
            if not supabase_url or not anon:
                raise SmokeError(
                    "Supabase auth mode: pass --supabase-url and --supabase-anon-key (or set in .env)"
                )
            resp = self.http.post(
                f"{supabase_url.rstrip('/')}/auth/v1/token",
                params={"grant_type": "password"},
                json={"email": email, "password": password},
                headers={"apikey": anon},
            )
            token = self._json(resp)["access_token"]
        self.auth = {"Authorization": f"Bearer {token}"}
        me = self.get("/auth/me")
        ok(f"logged in as {me['email']} ({mode})")

    def signal_cycle(self) -> None:
        step("Citizen signal → map")
        parcels = self.get("/parcels", status="OK")["features"]
        check(bool(parcels), f"{len(parcels)} parcels in status OK available")
        target = parcels[int(time.time()) % len(parcels)]["properties"]
        hit = self.get("/parcels/search", q=target["cadastral_number"])[0]
        last_id = self.get("/events")["last_id"]

        body: dict[str, Any] = {
            "lat": hit["centroid"]["lat"],
            "lon": hit["centroid"]["lon"],
            "category": "DUMP",
            "description": "E2E smoke: строительный мусор у дороги",
            "lang": self.args.lang,
            "photos": 1,
        }
        if self.args.chat_id:
            body["chat_id"] = self.args.chat_id
        sim = self.post("/dev/simulate-signal", body, service=True)
        signal = sim["signal"]
        check(
            signal["parcel_id"] == hit["id"],
            f"{signal['tracking_code']} bound to parcel {hit['cadastral_number']}",
        )
        check(sim["parcel_status"] == "UNDER_CHECK", "parcel OK → UNDER_CHECK")
        check(signal["photos_count"] == 1, "photo stored")
        events = {e["type"] for e in self.get("/events", since=last_id)["items"]}
        check(
            {"signal.created", "parcel.status_changed"} <= events,
            f"realtime events emitted: {sorted(events)}",
        )

        step("Inspector processes the case")
        detail = self.post(
            f"/signals/{signal['id']}/transitions",
            {"to": "CONFIRMED", "comment": "E2E: нарушение подтверждено"},
        )
        check(detail["status"] == "CONFIRMED", "signal CONFIRMED (citizen notified)")
        parcel = self.get(f"/parcels/{hit['id']}")
        check(parcel["status"] == "VIOLATION", f"parcel VIOLATION, deadline {parcel['deadline_at'][:10]}")
        bad = self.http.post(
            f"{self.api}/parcels/{hit['id']}/transitions",
            json={"to": "RESOLVED", "comment": "skip"},
            headers=self.auth,
        )
        check(bad.status_code == 409, "invalid transition VIOLATION → RESOLVED rejected with 409")
        parcel = self.post(
            f"/parcels/{hit['id']}/transitions", {"to": "IN_REMEDIATION", "comment": "E2E: предписание"}
        )
        check(parcel["status"] == "IN_REMEDIATION", "parcel → IN_REMEDIATION (citizen notified)")
        refused = self.http.post(
            f"{self.api}/parcels/{hit['id']}/transitions",
            json={"to": "RESOLVED", "comment": "E2E"},
            headers=self.auth,
        )
        check(refused.status_code == 422, "«resolved» without evidence refused (EVIDENCE_REQUIRED)")
        upload = self.http.post(
            f"{self.api}/parcels/{hit['id']}/photos",
            files=[
                (
                    "files",
                    (
                        "evidence.jpg",
                        jpeg_with_gps(hit["centroid"]["lat"], hit["centroid"]["lon"]),
                        "image/jpeg",
                    ),
                )
            ],
            headers=self.auth,
        )
        check(upload.status_code == 201, "inspector photo with GPS on the parcel uploaded as evidence")
        for target_status in ("RESOLVED",):
            parcel = self.post(
                f"/parcels/{hit['id']}/transitions", {"to": target_status, "comment": f"E2E: {target_status}"}
            )
            check(parcel["status"] == target_status, f"parcel → {target_status} (citizen notified)")
        check(len(parcel["history"]) >= 4, f"audit trail has {len(parcel['history'])} entries")

    def application_cycle(self) -> None:
        step("Application status push")
        apps = self.get("/applications", status="UNDER_REVIEW")["items"]
        if not apps:
            ok("no application in UNDER_REVIEW — skipped")
            return
        app = apps[0]
        result = self.post(
            f"/applications/{app['id']}/transitions",
            {
                "to": "INSPECTION_SCHEDULED",
                "comment_ru": "E2E: назначен выезд инспектора",
                "comment_kk": "E2E: инспектордың барып шығуы тағайындалды",
                "inspection_date": time.strftime("%Y-%m-%d", time.localtime(time.time() + 3 * 86400)),
            },
        )
        check(
            result["status"] == "INSPECTION_SCHEDULED",
            f"{app['tracking_number']} → INSPECTION_SCHEDULED ({result['subscribers_count']} subscribers pushed)",
        )

    def run(self) -> None:
        self.health()
        self.login()
        self.signal_cycle()
        if self.args.with_application:
            self.application_cycle()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--service-key")
    parser.add_argument("--email")
    parser.add_argument("--password")
    parser.add_argument("--supabase-url")
    parser.add_argument("--supabase-anon-key")
    parser.add_argument("--chat-id", type=int, help="Telegram chat id that should receive notifications")
    parser.add_argument("--lang", choices=["ru", "kk"], default="ru")
    parser.add_argument("--with-application", action="store_true", help="Also change an application status")
    args = parser.parse_args()
    started = time.perf_counter()
    try:
        Smoke(args).run()
    except (SmokeError, httpx.HTTPError) as exc:
        print(f"\n{RED}✗ E2E smoke FAILED:{RESET} {exc}")
        return 1
    print(
        f"\n{GREEN}✓ E2E smoke passed{RESET} in {time.perf_counter() - started:.1f}s against {args.base_url}"
    )
    print(f"{DIM}Demo data changed — run `make demo-reset` before presenting.{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
