# twig-precep-reader-v1

Script Python che legge un foglio Google Spreadsheet contenente i dati di un pre-cep di Twig e lo esporta in un file JSON strutturato.

## GitHub


## Esempio
$ uv run main.py "https://..." --sheet 1

## Struttura attesa del foglio

| Cella | Campo |
|-------|-------|
| B1 | Codice progetto |
| B2 | Inizio progetto |
| B3 | Fine progetto |
| D1 | Link CEP |
| D2 | Titolo preventivo |
| D3 | Descrizione preventivo |
| A5:I5 | Intestazioni delle colonne delle righe |
| A6:I… | Righe del preventivo |

## Requisiti

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) per la gestione delle dipendenze

## Installazione

```bash
uv sync
```

## Configurazione OAuth (una tantum)

Lo script accede a Google Sheets tramite OAuth 2.0 con flusso desktop. È necessario un file di credenziali scaricato da Google Cloud Console.

1. Vai su [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un progetto (o selezionane uno esistente)
3. Abilita l'API **Google Sheets**: *APIs & Services → Enable APIs → Google Sheets API*
4. Crea le credenziali: *APIs & Services → Credentials → Create Credentials → OAuth client ID*
   - Tipo applicazione: **Desktop app**
5. Scarica il file JSON e salvalo come `credentials.json` nella directory del progetto
6. Se l'app è in modalità test, aggiungi il tuo account Google come *Test user* in *OAuth consent screen*

## Utilizzo

```bash
uv run main.py "<URL_FOGLIO>" [--credentials credentials.json] [--sheet 0]
```

### Argomenti

| Argomento | Default | Descrizione |
|-----------|---------|-------------|
| `url` | _(obbligatorio)_ | URL del file Google Spreadsheet |
| `--credentials` | `credentials.json` | File OAuth client secrets da Google Cloud Console |
| `--sheet` | `0` | Indice del foglio da leggere (0 = primo foglio) |

Il nome del file JSON di output viene derivato automaticamente dal titolo del file su Google Drive: spazi sostituiti da `_`, tutto minuscolo, estensione `.json`. Ad esempio `"Preventivo Cliente XYZ 2026"` → `preventivo_cliente_xyz_2026.json`.

### Esempio

```bash
uv run main.py "https://docs.google.com/spreadsheets/d/..." --sheet 1
```

Al primo avvio si apre il browser per autorizzare l'accesso. Dopo il consenso, il token viene salvato in `token.json` e riutilizzato automaticamente nelle esecuzioni successive (con refresh automatico alla scadenza).

## Output JSON

```json
{
  "codice_progetto": "PRJ-001",
  "inizio_progetto": "2026-01-01",
  "fine_progetto": "2026-06-30",
  "link_cep": "https://...",
  "titolo_preventivo": "Titolo del preventivo",
  "descrizione_preventivo": "Descrizione estesa...",
  "righe": [
    {
      "colonna a": "valore",
      "colonna b": "valore",
      "...": "..."
    }
  ]
}
```

Le chiavi dell'array `righe` corrispondono ai valori nell'intervallo **A5:I5** del foglio, normalizzati in minuscolo.

## File sensibili

Aggiungere al `.gitignore`:

```
credentials.json
token.json
```

`token.json` contiene il token OAuth dell'utente e non va mai committato.
