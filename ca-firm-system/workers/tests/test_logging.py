import json
import logging

from ca_workers.logging_setup import JsonFormatter


def test_json_formatter_outputs_valid_json() -> None:
    rec = logging.LogRecord("w", logging.INFO, "f", 1, "hello %s", ("x",), None)
    out = json.loads(JsonFormatter().format(rec))
    assert out["message"] == "hello x"
    assert out["level"] == "INFO"
