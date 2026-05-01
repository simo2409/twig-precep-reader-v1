import argparse
import json
import re
import sys
from pathlib import Path

import gspread
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
TOKEN_FILE = "token.json"


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


def read_metadata(sheet: gspread.Worksheet) -> dict:
    return {
        "codice_progetto": sheet.acell("B1").value,
        "inizio_progetto": sheet.acell("B2").value,
        "fine_progetto": sheet.acell("B3").value,
        "link_cep": sheet.acell("D1").value,
        "titolo_preventivo": sheet.acell("D2").value,
        "descrizione_preventivo": sheet.acell("D3").value,
    }


def read_rows(sheet: gspread.Worksheet) -> list[dict]:
    all_values = sheet.get("A5:I")
    if not all_values:
        return []

    headers = [h.lower() for h in all_values[0]]
    rows = []
    for row in all_values[1:]:
        # Padda la riga se ha meno colonne degli header
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

    output_file = title_to_filename(spreadsheet.title)
    metadata = read_metadata(sheet)
    rows = read_rows(sheet)

    result = {**metadata, "righe": rows}

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"JSON salvato in: {output_file}")
    print(f"  Metadati: {len(metadata)} campi")
    print(f"  Righe esportate: {len(rows)}")



if __name__ == "__main__":
    main()
