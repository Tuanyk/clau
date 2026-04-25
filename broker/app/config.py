"""Loads broker configuration from env vars set by entrypoint.sh.

Each provider is opt-in: missing creds = the matching router returns 503,
the others keep working. Never log or echo credential values.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

SECRETS_DIR = Path("/run/broker-secrets")


def _load_secret_env_files() -> None:
    if not SECRETS_DIR.is_dir():
        return
    for env_file in sorted(SECRETS_DIR.glob("*.env")):
        load_dotenv(env_file, override=True)


_load_secret_env_files()


def _autodetect_gcp_sa() -> str | None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
    if not SECRETS_DIR.is_dir():
        return None
    for name in ("gcp-sa.json", "service-account.json", "gcp.json"):
        p = SECRETS_DIR / name
        if p.is_file():
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(p)
            return str(p)
    return None


class Meta:
    @property
    def access_token(self) -> str | None:
        return os.environ.get("META_ACCESS_TOKEN")

    @property
    def graph_version(self) -> str:
        return os.environ.get("META_GRAPH_VERSION", "v21.0")

    @property
    def configured(self) -> bool:
        return bool(self.access_token)


class GoogleAds:
    @property
    def configured(self) -> bool:
        return all(
            os.environ.get(k)
            for k in (
                "GOOGLE_ADS_DEVELOPER_TOKEN",
                "GOOGLE_ADS_CLIENT_ID",
                "GOOGLE_ADS_CLIENT_SECRET",
                "GOOGLE_ADS_REFRESH_TOKEN",
            )
        )

    def sdk_config(self) -> dict:
        cfg = {
            "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
            "use_proto_plus": True,
        }
        login_cid = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        if login_cid:
            cfg["login_customer_id"] = login_cid
        return cfg


class GoogleSA:
    """Service account-backed providers: GA4, GSC."""

    @property
    def configured(self) -> bool:
        return _autodetect_gcp_sa() is not None

    @property
    def credentials_path(self) -> str | None:
        return _autodetect_gcp_sa()


@lru_cache(maxsize=1)
def settings() -> dict:
    _autodetect_gcp_sa()
    return {
        "meta": Meta(),
        "google_ads": GoogleAds(),
        "google_sa": GoogleSA(),
    }


def configured_providers() -> list[str]:
    s = settings()
    out = []
    if s["meta"].configured:
        out.append("meta")
    if s["google_ads"].configured:
        out.append("google_ads")
    if s["google_sa"].configured:
        out.extend(["ga4", "gsc", "gtm"])
    return out
