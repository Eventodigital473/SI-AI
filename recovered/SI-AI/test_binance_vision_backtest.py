import hashlib
import io
import zipfile
from datetime import datetime, timezone

import pytest

import binance_vision_backtest as vision


class FakeResponse:
    def __init__(self, content=b"", text=""):
        self.content = content
        self.text = text

    def raise_for_status(self):
        return None


def make_zip(csv_text):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("sample.csv", csv_text)
    return buffer.getvalue()


def test_month_range_includes_each_month_once():
    months = list(vision._months_between(
        datetime(2026, 5, 5, tzinfo=timezone.utc),
        datetime(2026, 11, 1, tzinfo=timezone.utc),
    ))
    assert months == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]


def test_verified_zip_checks_sha256_and_parses_single_csv():
    payload = make_zip("open_time,open,high,low,close,volume,close_time\n1,2,3,1,2,4,59999\n")
    digest = hashlib.sha256(payload).hexdigest()
    calls = []

    def fake_get(url, timeout):
        calls.append(url)
        if url.endswith(".CHECKSUM"):
            return FakeResponse(text=f"{digest}  sample.zip")
        return FakeResponse(content=payload)

    rows, actual = vision._download_verified_zip("monthly/klines/BTCUSDT/1h/sample.zip", get=fake_get)
    assert actual == digest
    assert rows[0][0] == "open_time"
    assert rows[1][0] == "1"
    assert len(calls) == 2


def test_verified_zip_rejects_checksum_mismatch():
    payload = make_zip("1,2,3,1,2,4,59999\n")

    def fake_get(url, timeout):
        if url.endswith(".CHECKSUM"):
            return FakeResponse(text=("0" * 64) + " sample.zip")
        return FakeResponse(content=payload)

    with pytest.raises(ValueError, match="checksum mismatch"):
        vision._download_verified_zip("monthly/klines/BTCUSDT/1h/sample.zip", get=fake_get)


def test_verified_zip_rejects_path_traversal():
    with pytest.raises(ValueError, match="Invalid Binance Vision archive path"):
        vision._download_verified_zip("../private.zip", get=lambda *a, **k: None)


def test_numeric_csv_parser_skips_one_header_and_rejects_later_bad_rows():
    parsed = vision._parse_numeric_rows(
        [["calc_time", "funding_interval_hours", "last_funding_rate"],
         ["1000", "8", "0.0001"]],
        expected_columns=3,
        label="funding",
    )
    assert parsed == [[1000.0, 8.0, 0.0001]]

    with pytest.raises(ValueError, match="non-numeric CSV row"):
        vision._parse_numeric_rows(
            [["1000", "8", "0.0001"], ["bad", "8", "0.0002"]],
            expected_columns=3,
            label="funding",
        )


def test_symbol_validation_is_futures_only_and_deduplicates():
    assert vision._validate_symbols(["BTC/USDT", "ETH/USDT", "BTC/USDT"]) == [
        "BTC/USDT", "ETH/USDT"
    ]
    with pytest.raises(ValueError):
        vision._validate_symbols(["BTC/USD"])
    with pytest.raises(ValueError):
        vision._validate_symbols(["BTC/USDT", "btc/USDT"])
