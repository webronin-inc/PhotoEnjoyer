"""Мини-клиент для тестов WSGI-приложения без сети."""
import io
import json
from urllib.parse import urlencode


class Resp:
    def __init__(self, status, headers, body):
        self.status, self.headers, self.raw = status, dict(headers), body

    @property
    def json(self):
        return json.loads(self.raw.decode("utf-8"))


def call(app, method, path, data=None, token=None, raw=None, query=None, ip="1.2.3.4"):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else b"")
    qs = urlencode(query or {})
    env = {"REQUEST_METHOD": method, "PATH_INFO": path, "QUERY_STRING": qs,
           "CONTENT_LENGTH": str(len(body)), "wsgi.input": io.BytesIO(body),
           "REMOTE_ADDR": ip, "CONTENT_TYPE": "application/json"}
    if token:
        env["HTTP_AUTHORIZATION"] = "Bearer " + token
    out = {}

    def sr(status, headers):
        out["status"] = int(status.split()[0])
        out["headers"] = headers

    chunks = app(env, sr)
    return Resp(out["status"], out["headers"], b"".join(chunks))
