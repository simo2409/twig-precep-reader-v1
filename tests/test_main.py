import time
from unittest.mock import MagicMock, patch

import gspread
import pytest

from main import (
    _extract_cell_value,
    _is_retryable,
    extract_spreadsheet_id,
    read_metadata,
    read_rows,
    title_to_filename,
)


class TestExtractSpreadsheetId:
    def test_extracts_id_from_standard_url(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms/edit"
        assert extract_spreadsheet_id(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"

    def test_extracts_id_with_query_params(self):
        url = "https://docs.google.com/spreadsheets/d/abc123/edit?usp=sharing"
        assert extract_spreadsheet_id(url) == "abc123"

    def test_raises_for_non_spreadsheet_url(self):
        with pytest.raises(ValueError, match="Impossibile estrarre"):
            extract_spreadsheet_id("https://google.com/not-a-spreadsheet")

    def test_raises_for_empty_string(self):
        with pytest.raises(ValueError):
            extract_spreadsheet_id("")


class TestTitleToFilename:
    def test_converts_spaces_to_underscores(self):
        assert title_to_filename("My Project") == "my_project.json"

    def test_lowercases_title(self):
        assert title_to_filename("UPPER") == "upper.json"

    def test_collapses_multiple_spaces(self):
        assert title_to_filename("too  many   spaces") == "too_many_spaces.json"

    def test_adds_json_extension(self):
        assert title_to_filename("simple").endswith(".json")


class TestExtractCellValue:
    def test_extracts_value_from_populated_range(self):
        assert _extract_cell_value([["hello"]]) == "hello"

    def test_returns_none_for_empty_range(self):
        assert _extract_cell_value([]) is None

    def test_returns_none_for_empty_row(self):
        assert _extract_cell_value([[]]) is None


class TestIsRetryable:
    def _api_error(self, status: int) -> gspread.exceptions.APIError:
        mock_resp = MagicMock()
        mock_resp.status_code = status
        mock_resp.json.return_value = {"error": {"code": status, "message": "error"}}
        return gspread.exceptions.APIError(mock_resp)

    def test_retries_on_429(self):
        assert _is_retryable(self._api_error(429)) is True

    def test_retries_on_500(self):
        assert _is_retryable(self._api_error(500)) is True

    def test_retries_on_503(self):
        assert _is_retryable(self._api_error(503)) is True

    def test_does_not_retry_on_400(self):
        assert _is_retryable(self._api_error(400)) is False

    def test_does_not_retry_on_404(self):
        assert _is_retryable(self._api_error(404)) is False

    def test_does_not_retry_on_non_api_error(self):
        assert _is_retryable(ValueError("bad input")) is False


_FULL_BATCH_RESULT = [
    [["P001"]],
    [["2024-01-01"]],
    [["2024-12-31"]],
    [["http://cep.example"]],
    [["Titolo test"]],
    [["Descrizione test"]],
]


class TestReadMetadata:
    def _sheet(self, batch_result=None):
        sheet = MagicMock()
        sheet.batch_get.return_value = batch_result or _FULL_BATCH_RESULT
        return sheet

    def test_uses_batch_get_not_acell(self):
        sheet = self._sheet()
        read_metadata(sheet)
        sheet.batch_get.assert_called_once()
        sheet.acell.assert_not_called()

    def test_batch_get_called_with_six_ranges(self):
        sheet = self._sheet()
        read_metadata(sheet)
        ranges = sheet.batch_get.call_args[0][0]
        assert len(ranges) == 6

    def test_returns_all_six_fields(self):
        sheet = self._sheet()
        assert read_metadata(sheet) == {
            "codice_progetto": "P001",
            "inizio_progetto": "2024-01-01",
            "fine_progetto": "2024-12-31",
            "link_cep": "http://cep.example",
            "titolo_preventivo": "Titolo test",
            "descrizione_preventivo": "Descrizione test",
        }

    def test_handles_empty_cells(self):
        sheet = self._sheet([[], [], [], [], [], []])
        result = read_metadata(sheet)
        for key in [
            "codice_progetto",
            "inizio_progetto",
            "fine_progetto",
            "link_cep",
            "titolo_preventivo",
            "descrizione_preventivo",
        ]:
            assert result[key] is None

    @patch("time.sleep")
    def test_retries_on_429_then_succeeds(self, _sleep):
        sheet = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.json.return_value = {"error": {"code": 429, "message": "rate limited"}}

        calls = [0]

        def side_effect(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise gspread.exceptions.APIError(mock_resp)
            return _FULL_BATCH_RESULT

        sheet.batch_get.side_effect = side_effect
        result = read_metadata(sheet)
        assert calls[0] == 2
        assert result["codice_progetto"] == "P001"

    @patch("time.sleep")
    def test_raises_after_max_retries(self, _sleep):
        sheet = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.json.return_value = {"error": {"code": 503, "message": "unavailable"}}
        sheet.batch_get.side_effect = gspread.exceptions.APIError(mock_resp)

        with pytest.raises(gspread.exceptions.APIError):
            read_metadata(sheet)


class TestReadRows:
    def test_returns_empty_list_when_no_data(self):
        sheet = MagicMock()
        sheet.get.return_value = []
        assert read_rows(sheet) == []

    def test_parses_header_and_rows(self):
        sheet = MagicMock()
        sheet.get.return_value = [
            ["Nome", "Ore", "Costo"],
            ["Task 1", "10", "100"],
            ["Task 2", "5", "50"],
        ]
        assert read_rows(sheet) == [
            {"nome": "Task 1", "ore": "10", "costo": "100"},
            {"nome": "Task 2", "ore": "5", "costo": "50"},
        ]

    def test_pads_short_rows(self):
        sheet = MagicMock()
        sheet.get.return_value = [
            ["Nome", "Ore", "Costo"],
            ["Task 1"],
        ]
        assert read_rows(sheet) == [{"nome": "Task 1", "ore": "", "costo": ""}]

    def test_lowercases_headers(self):
        sheet = MagicMock()
        sheet.get.return_value = [["NOME", "ORE"], ["Task", "5"]]
        result = read_rows(sheet)
        assert "nome" in result[0]
        assert "ore" in result[0]

    @patch("time.sleep")
    def test_retries_on_500_then_succeeds(self, _sleep):
        sheet = MagicMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.json.return_value = {"error": {"code": 500, "message": "server error"}}

        calls = [0]

        def side_effect(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise gspread.exceptions.APIError(mock_resp)
            return [["Nome"], ["Task 1"]]

        sheet.get.side_effect = side_effect
        result = read_rows(sheet)
        assert calls[0] == 2
        assert result == [{"nome": "Task 1"}]
