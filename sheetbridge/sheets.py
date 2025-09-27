from typing import Dict, List

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import settings

def _service(creds: Credentials):
    return build("sheets", "v4", credentials=creds, cache_discovery=False)

def get_header(creds: Credentials) -> List[str]:
    svc = _service(creds)
    rng = f"{settings.GOOGLE_WORKSHEET}!1:1"
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=settings.GOOGLE_SHEET_ID, range=rng)
        .execute()
    )
    return [h.strip() for h in res.get("values", [[]])[0]]


def fetch_sheet(creds: Credentials) -> List[Dict]:
    svc = _service(creds)
    rng = f"{settings.GOOGLE_WORKSHEET}!A:Z"
    res = (
        svc.spreadsheets()
        .values()
        .get(spreadsheetId=settings.GOOGLE_SHEET_ID, range=rng)
        .execute()
    )
    values = res.get("values", [])
    if not values:
        return []
    header = [h.strip() for h in values[0]]
    rows = []
    for raw in values[1:]:
        row = {header[i]: (raw[i] if i < len(raw) else None) for i in range(len(header))}
        rows.append(row)
    return rows

def append_row(creds: Credentials, row: Dict):
    header = get_header(creds)
    values = [row.get(column, None) for column in header]
    svc = _service(creds)
    rng = f"{settings.GOOGLE_WORKSHEET}!A:Z"
    body = {"values": [values]}
    svc.spreadsheets().values().append(
        spreadsheetId=settings.GOOGLE_SHEET_ID,
        range=rng,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def append_rows(creds: Credentials, rows: list[Dict]):
    header = get_header(creds)
    values = [[row.get(column, None) for column in header] for row in rows]
    svc = _service(creds)
    rng = f"{settings.GOOGLE_WORKSHEET}!A:Z"
    body = {"values": values}
    svc.spreadsheets().values().append(
        spreadsheetId=settings.GOOGLE_SHEET_ID,
        range=rng,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body,
    ).execute()


def fetch_sheet_with_auto_creds(creds: Credentials) -> list[dict]:
    return fetch_sheet(creds)
