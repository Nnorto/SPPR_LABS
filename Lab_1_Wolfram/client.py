"""HTTPS-клиент Full Results API, только стандартная библиотека Python."""
import json
import logging
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://api.wolframalpha.com/v2/query"


class RequestFailure(Exception):
    """Безопасное сообщение: URL с ключом никогда не попадает в лог."""

    def __init__(self, message, raw_body=None):
        super().__init__(message)
        self.raw_body = raw_body


class WolframClient:
    def __init__(self, config, opener=urlopen, sleeper=time.sleep):
        self.config = config
        self.opener = opener
        self.sleep = sleeper

    def query(self, text):
        params = {"input": text, "output": "json", "format": "plaintext"}
        # При обычном запуске ключ читается из config.json.
        # В защищённой проверочной среде допускается его подстановка HTTPS-прокси.
        if self.config.get("appid"):
            params["appid"] = self.config["appid"]
        request = Request(
            ENDPOINT + "?" + urlencode(params),
            headers={"Accept": "application/json", "User-Agent": "EducationalLab/1.0"},
        )
        retries = self.config["retries"]
        for attempt in range(retries + 1):
            try:
                with self.opener(request, timeout=self.config["timeout_seconds"]) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    raise RequestFailure("Сервер вернул не JSON.", raw) from None
                if not isinstance(data, dict):
                    raise RequestFailure("Корень ответа API не является объектом.", raw)
                return data
            except HTTPError as error:
                body = error.read().decode("utf-8", errors="replace")
                can_retry = error.code == 429 or 500 <= error.code < 600
                if not can_retry or attempt == retries:
                    raise RequestFailure(f"HTTP {error.code}", body) from None
                logging.warning("HTTP %s; повтор %s/%s", error.code, attempt + 1, retries)
            except (URLError, TimeoutError, socket.timeout, ConnectionError, OSError):
                if attempt == retries:
                    raise RequestFailure("Сетевая ошибка или тайм-аут.") from None
                logging.warning("Сетевая ошибка; повтор %s/%s", attempt + 1, retries)
            self.sleep(2 ** attempt)
        raise RequestFailure("Не удалось выполнить запрос.")
