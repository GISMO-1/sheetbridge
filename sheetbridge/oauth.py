from __future__ import annotations

import json
import os
import pathlib
from typing import Optional

from google.oauth2.credentials import Credentials
from google.oauth2.service_account import Credentials as SACreds
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES_READ = ["https://www.googleapis.com/auth/spreadsheets.readonly"]


def _token_path(path: str) -> pathlib.Path:
    token_path = pathlib.Path(path)
    token_path.parent.mkdir(parents=True, exist_ok=True)
    return token_path


def creds_from_service_account(json_str: str, subject: Optional[str]) -> Credentials:
    info = json.loads(json_str)
    service_creds = SACreds.from_service_account_info(info, scopes=SCOPES_READ)
    if subject:
        service_creds = service_creds.with_subject(subject)
    return service_creds.with_scopes(SCOPES_READ)


def creds_from_oauth(client_secrets_path: str, token_store: str) -> Credentials:
    token_path = _token_path(token_store)
    if token_path.exists():
        return Credentials.from_authorized_user_file(str(token_path), SCOPES_READ)
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets_path,
        scopes=SCOPES_READ,
    )
    creds = flow.run_console()
    token_path.write_text(creds.to_json())
    return creds


def resolve_credentials(
    oauth_client_path: Optional[str],
    service_json: Optional[str],
    delegated_subject: Optional[str],
    token_store: str,
) -> Optional[Credentials]:
    if service_json:
        return creds_from_service_account(service_json, delegated_subject)
    if oauth_client_path:
        if not os.path.exists(oauth_client_path):
            return None
        return creds_from_oauth(oauth_client_path, token_store)
    return None
