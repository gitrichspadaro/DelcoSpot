"""Broadcastify developer API request signing.

Each developer key gives three values (Developer Portal > API Keys):
  BCFY_KEY_ID   -> JWT header "kid" (the key's ID, e.g. cf8eca9)
  BCFY_ISSUER   -> JWT payload "iss" (the app identity, e.g. 6aeca7d5cec5d)
  BCFY_SECRET   -> HMAC-SHA256 signing secret (shown once, at creation or rotation)

Optional, only for endpoints that need a signed-in user (for example Live Calls):
  BCFY_USER_ID  -> JWT payload "sub"
  BCFY_USER_TOKEN -> JWT payload "utk"

Each API request carries a short-lived HS256 JWT, sent as
"Authorization: Bearer <token>". Mint a fresh token for each request.

Values come from environment variables only; nothing is stored in the repo.
Standard library only, so no new requirements.txt entries.

Command line, to print a token for manual testing:
  python broadcastify_auth.py
"""
import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

TOKEN_LIFETIME_SECONDS = 300  # short-lived; a fresh token is minted per request

# Archive requests may span at most this many seconds (8 hours), per the Group Archives docs.
MAX_ARCHIVE_WINDOW_SECONDS = 28800


class BroadcastifyConfigError(RuntimeError):
    pass


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _load_config() -> dict:
    required = {
        "kid": "BCFY_KEY_ID",
        "iss": "BCFY_ISSUER",
        "secret": "BCFY_SECRET",
    }
    values = {key: os.environ.get(env, "").strip() for key, env in required.items()}
    missing = [env for key, env in required.items() if not values[key]]
    if missing:
        raise BroadcastifyConfigError("Missing Broadcastify settings: " + ", ".join(missing))
    # Optional user claims. Only added to the token when both are set.
    values["sub"] = os.environ.get("BCFY_USER_ID", "").strip()
    values["utk"] = os.environ.get("BCFY_USER_TOKEN", "").strip()
    return values


def make_token(now: Optional[int] = None, config: Optional[dict] = None) -> str:
    """Return a signed HS256 JWT for one API request."""
    cfg = config or _load_config()
    issued = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT", "kid": cfg["kid"]}
    payload = {"iss": cfg["iss"], "iat": issued, "exp": issued + TOKEN_LIFETIME_SECONDS}
    if cfg.get("sub") and cfg.get("utk"):
        payload["sub"] = cfg["sub"]
        payload["utk"] = cfg["utk"]

    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    )
    # The portal gives the secret as text, used as its UTF-8 bytes.
    # The docs do not state the format. If the first live call returns 401, try BCFY_SECRET_IS_HEX=1.
    key = cfg["secret"].encode("utf-8")
    if os.environ.get("BCFY_SECRET_IS_HEX") == "1":
        key = bytes.fromhex(cfg["secret"])
    signature = hmac.new(key, signing_input.encode("ascii"), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


def auth_headers(now: Optional[int] = None) -> dict:
    """Headers to attach to a Broadcastify API request."""
    return {"Authorization": "Bearer " + make_token(now=now)}


def group_archive_url(group_id: str, start_ts: int, end_ts: int) -> str:
    """URL for GET /calls/v1/group_archives/{groupId}/{start}/{end}.

    group_id is "{sid}-{talkgroup}", for example "13264-224".
    """
    if end_ts <= start_ts:
        raise ValueError("end_ts must be after start_ts")
    if end_ts - start_ts > MAX_ARCHIVE_WINDOW_SECONDS:
        raise ValueError("archive window may not exceed 8 hours")
    return f"https://api.bcfy.io/calls/v1/group_archives/{group_id}/{start_ts}/{end_ts}"


if __name__ == "__main__":
    print(make_token())
