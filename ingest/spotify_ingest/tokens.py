"""Token file shared by the login script and the ingester."""

import json
import os
import time
from pathlib import Path

# Seconds shaved off the real expiry so a token never expires mid-request.
EXPIRY_MARGIN = 60


def token_path() -> Path:
    return Path(os.environ.get("SPOTIFY_TOKEN_PATH", "/secrets/token.json"))


def load() -> dict:
    path = token_path()
    if not path.exists():
        raise FileNotFoundError(
            f"No token file at {path}. Run the first login (see README) before ingesting."
        )
    return json.loads(path.read_text())


def save(refresh_token: str, access_token: str, expires_in: int) -> None:
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "refresh_token": refresh_token,
        "access_token": access_token,
        "expires_at": time.time() + expires_in - EXPIRY_MARGIN,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)
