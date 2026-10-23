"""Автотесты без сети и без ключа: python3 -m unittest -v."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError, URLError
from unittest.mock import Mock

from client import WolframClient, RequestFailure
from configuration import load_config
from demo_data import synthetic_response
from main import run_batch
from processing import extract
from queries import QUERIES
from storage import redact


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


class ProcessingTests(unittest.TestCase):
    def test_ok_and_all_pods(self):
        result = extract(synthetic_response("physics", "test"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["pods"]), 2)
        self.assertTrue(result["pods"][1]["primary"])

    def test_no_result(self):
        self.assertEqual(extract({"queryresult": {"success": False}})["status"], "no_result")

    def test_api_error_object(self):
        result = extract({"queryresult": {"error": {"code": "1", "msg": "Bad appid"}}})
        self.assertEqual(result["status"], "api_error")
        self.assertEqual(result["message"], "Bad appid")

    def test_boolean_api_error(self):
        self.assertEqual(extract({"queryresult": {"error": True}})["status"], "api_error")

    def test_missing_root(self):
        self.assertEqual(extract({})["status"], "invalid_response")

    def test_success_without_text(self):
        self.assertEqual(extract({"queryresult": {"success": True, "pods": []}})["status"], "no_text")

    def test_invalid_pods(self):
        self.assertEqual(extract({"queryresult": {"success": True, "pods": 5}})["status"],
                         "invalid_response")

    def test_empty_and_malformed_subpods(self):
        result = extract({"queryresult": {"success": True, "pods": [
            None, {"subpods": [None, {"plaintext": ""}, {"plaintext": 5}]}]}})
        self.assertEqual(result["status"], "no_text")

    def test_string_boolean(self):
        result = extract({"queryresult": {"success": "true", "error": "false",
                                         "pods": [{"subpods": [{"plaintext": "2"}]}]}})
        self.assertEqual(result["status"], "ok")


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.config = {"appid": "UNIT_TEST_KEY", "timeout_seconds": 30, "retries": 2}

    def test_https_json_request(self):
        opener = Mock(return_value=FakeResponse(b'{"queryresult":{"success":false}}'))
        client = WolframClient(self.config, opener=opener)
        client.query("x^2 + 2")
        request = opener.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://api.wolframalpha.com/v2/query?"))
        self.assertIn("output=json", request.full_url)
        self.assertIn("appid=UNIT_TEST_KEY", request.full_url)
        self.assertIn("input=x%5E2+%2B+2", request.full_url)
        self.assertEqual(opener.call_args.kwargs["timeout"], 30)

    def test_retry_network(self):
        opener = Mock(side_effect=[URLError("offline"), FakeResponse(b'{"queryresult":{}}')])
        sleep = Mock()
        WolframClient(self.config, opener=opener, sleeper=sleep).query("2+2")
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_network_exhaustion_safe_message(self):
        opener = Mock(side_effect=URLError("URL includes UNIT_TEST_KEY"))
        with self.assertRaises(RequestFailure) as caught:
            WolframClient(self.config, opener=opener, sleeper=Mock()).query("2+2")
        self.assertNotIn("UNIT_TEST_KEY", str(caught.exception))
        self.assertEqual(opener.call_count, 3)

    def test_timeout(self):
        config = {**self.config, "retries": 0}
        with self.assertRaises(RequestFailure):
            WolframClient(config, opener=Mock(side_effect=TimeoutError())).query("2+2")

    def test_401_no_retry(self):
        error = HTTPError("https://example.invalid", 401, "Unauthorized", {}, io.BytesIO(b"denied"))
        opener = Mock(side_effect=error)
        with self.assertRaisesRegex(RequestFailure, "HTTP 401"):
            WolframClient(self.config, opener=opener).query("2+2")
        self.assertEqual(opener.call_count, 1)

    def test_429_retry(self):
        error = HTTPError("https://example.invalid", 429, "Limit", {}, io.BytesIO(b"limit"))
        opener = Mock(side_effect=[error, FakeResponse(b'{"queryresult":{}}')])
        WolframClient(self.config, opener=opener, sleeper=Mock()).query("2+2")
        self.assertEqual(opener.call_count, 2)

    def test_503_retry(self):
        error = HTTPError("https://example.invalid", 503, "Unavailable", {}, io.BytesIO(b"busy"))
        opener = Mock(side_effect=[error, FakeResponse(b'{"queryresult":{}}')])
        WolframClient(self.config, opener=opener, sleeper=Mock()).query("2+2")
        self.assertEqual(opener.call_count, 2)

    def test_non_json_body_kept(self):
        with self.assertRaises(RequestFailure) as caught:
            WolframClient(self.config, opener=Mock(return_value=FakeResponse(b"<html/>"))).query("x")
        self.assertEqual(caught.exception.raw_body, "<html/>")

    def test_non_object_json(self):
        with self.assertRaises(RequestFailure):
            WolframClient(self.config, opener=Mock(return_value=FakeResponse(b"[]"))).query("x")


class ConfigTests(unittest.TestCase):
    def check_config(self, data):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text(json.dumps(data), encoding="utf-8")
            return load_config(path)

    def test_valid(self):
        self.assertEqual(self.check_config({"appid": " unit-test "})["appid"], "unit-test")

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError, "Нет config.json"):
                load_config(Path(folder, "absent.json"))

    def test_bad_key(self):
        for key in ["", "PUT_YOUR_APPID_HERE", None, 42]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check_config({"appid": key})

    def test_bad_numeric_fields(self):
        for field, value in [("retries", 2.5), ("timeout_seconds", 0),
                             ("delay_seconds", -1), ("retries", True),
                             ("timeout_seconds", float("nan"))]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.check_config({"appid": "test", field: value})

    def test_non_object(self):
        with self.assertRaises(ValueError):
            self.check_config([])

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, "config.json")
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_config(path)


class BatchTests(unittest.TestCase):
    def test_fifteen_queries(self):
        self.assertEqual(len(QUERIES), 15)
        self.assertEqual(len({q[0] for q in QUERIES}), 15)
        self.assertEqual(QUERIES[0][2], "integrate x^2 sin^3 x dx")
        self.assertEqual(QUERIES[9][2], "translate hello to Russian")

    def test_demo_files(self):
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            rows = run_batch({}, folder, demo=True)
            self.assertEqual(len(rows), 15)
            self.assertEqual(sum(row["status"] == "ok" for row in rows), 7)
            self.assertTrue(all(row["mode"] == "demo" for row in rows))
            self.assertEqual(len(list(Path(folder, "raw").glob("*.json"))), 15)
            self.assertEqual(len(list(Path(folder, "extracted").glob("*.json"))), 15)
            report = Path(folder, "report.md").read_text(encoding="utf-8")
            self.assertIn("запросы к API не выполнялись", report)

    def test_continue_after_error(self):
        client = Mock()
        client.query.side_effect = [
            RequestFailure("failed"),
            synthetic_response("physics", "second"),
        ]
        with tempfile.TemporaryDirectory() as folder, redirect_stdout(io.StringIO()):
            rows = run_batch({"delay_seconds": 0}, folder, queries=QUERIES[:2], client=client)
            self.assertEqual([r["status"] for r in rows], ["request_error", "ok"])

    def test_secret_redacted(self):
        self.assertEqual(redact({"msg": ["key=secret"]}, "secret"),
                         {"msg": ["key=[REDACTED_APPID]"]})


if __name__ == "__main__":
    unittest.main()
