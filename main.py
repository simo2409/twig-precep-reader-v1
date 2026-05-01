import argparse
import json
import re
import sys
from pathlib import Path

import gspread
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_FILE = "token.json"

_METADATA_RANGES = ["B1", "B2", "B3", "D1", "D2", "D3"]
_METADATA_KEYS = [
    "codice_progetto",
    "inizio_progetto",
    "fine_progetto",
    "link_cep",
    "titolo_preventivo",
    "descrizione_preventivo",
]


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, gspread.exceptions.APIError):
        try:
            status = exc.response.status_code
            return status == 429 or status >= 500
        except AttributeError:
            return True
    return False


def _extract_cell_value(range_data: list) -> str | None:
    if range_data and range_data[0]:
        return range_data[0][0]
    return None


def extract_spreadsheet_id(url: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Impossibile estrarre l'ID dal URL: {url}")
    return match.group(1)


def get_credentials(client_secrets_file: str) -> Credentials:
    creds = None

    if Path(TOKEN_FILE).exists():
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
            creds = flow.run_local_server(port=0)
        Path(TOKEN_FILE).write_text(creds.to_json())

    return creds


def title_to_filename(title: str) -> str:
    return re.sub(r"\s+", "_", title).lower() + ".json"


def open_sheet(spreadsheet_id: str, client_secrets_file: str) -> gspread.Spreadsheet:
    creds = get_credentials(client_secrets_file)
    client = gspread.authorize(creds)
    return client.open_by_key(spreadsheet_id)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def read_metadata(sheet: gspread.Worksheet) -> dict:
    results = sheet.batch_get(_METADATA_RANGES)
    return {key: _extract_cell_value(data) for key, data in zip(_METADATA_KEYS, results)}


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def read_rows(sheet: gspread.Worksheet) -> list[dict]:
    all_values = sheet.get("A5:I")
    if not all_values:
        return []

    headers = [h.lower() for h in all_values[0]]
    rows = []
    for row in all_values[1:]:
        padded = row + [""] * (len(headers) - len(row))
        rows.append(dict(zip(headers, padded)))

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Legge un Google Spreadsheet e crea un file JSON."
    )
    parser.add_argument("url", help="URL del file Google Spreadsheet")
    parser.add_argument(
        "--credentials",
        default="credentials.json",
        help="Percorso del file OAuth client secrets scaricato da Google Cloud Console (default: credentials.json)",
    )
    parser.add_argument(
        "--sheet",
        default=0,
        type=int,
        help="Indice del foglio da leggere (default: 0, primo foglio)",
    )
    args = parser.parse_args()

    try:
        spreadsheet_id = extract_spreadsheet_id(args.url)
    except ValueError as e:
        print(f"Errore: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        spreadsheet = open_sheet(spreadsheet_id, args.credentials)
        sheet = spreadsheet.get_worksheet(args.sheet)
    except Exception as e:
        print(f"Errore nell'apertura del foglio: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        metadata = read_metadata(sheet)
        rows = read_rows(sheet)
    except Exception as e:
        print(f"Errore nella lettura dei dati: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    output_file = title_to_filename(spreadsheet.title)
    result = {**metadata, "righe": rows}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON salvato in: {output_file}")
    print(f"  Metadati: {len(metadata)} campi")
    print(f"  Righe esportate: {len(rows)}")


if __name__ == "__main__":
    main()
