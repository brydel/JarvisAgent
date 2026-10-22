"""Contrats de la passerelle ; aucune inference ni connexion externe."""
import http.client
import importlib.util
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("jarvis_model_bridge", Path(__file__).parents[1] / "server.py")
bridge = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = bridge
spec.loader.exec_module(bridge)
TOKEN = "test-only-not-a-real-secret-" * 2


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.srv = bridge.server(bridge.Settings(enabled=True, token=TOKEN, model="test-model"), 0)
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.thread.join(2)

    def request(self, data=None, method="POST", path="/v1/generate", headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.srv.server_port, timeout=3)
        h = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}
        h.update(headers or {})
        raw = json.dumps(data).encode() if data is not None else None
        c.request(method, path, raw, h)
        r = c.getresponse()
        result = r.status, json.loads(r.read())
        c.close()
        return result

    def test_health_is_not_provider_availability(self):
        status, body = self.request(method="GET", path="/health")
        self.assertEqual(status, 200)
        self.assertFalse(body["upstream_verified"])
        self.assertFalse(body["default_provider"])
        self.assertNotIn(TOKEN, json.dumps(body))

    def test_authentication_required(self):
        self.assertEqual(self.request({"prompt": "bonjour"}, headers={"Authorization": "bad"})[0], 401)

    def test_browser_origin_refused(self):
        self.assertEqual(self.request({"prompt": "bonjour"}, headers={"Origin": "http://localhost:7731"})[0], 403)

    def test_host_rebinding_refused(self):
        self.assertEqual(self.request({"prompt": "bonjour"}, headers={"Host": "evil.test"})[0], 403)

    def test_unknown_fields_and_tools_refused(self):
        for data in ({"prompt": "hello", "url": "http://example.test"}, {"prompt": "hello", "tools": []},
                     {"prompt": "hello", "model": "other"}, {"prompt": "hello", "max_tokens": True},
                     {"prompt": "hello", "max_tokens": 9999}, {"prompt": ""}, []):
            with self.subTest(data=data):
                self.assertEqual(self.request(data)[0], 400)

    def test_size_bounded(self):
        self.assertEqual(self.request({"prompt": "x" * 40000})[0], 413)

    def test_no_automatic_fallback(self):
        with patch.object(bridge, "generate", side_effect=bridge.BridgeError(502, "indisponible")) as mock:
            self.assertEqual(self.request({"prompt": "test"})[0], 502)
            self.assertEqual(mock.call_count, 1)

    def test_gate_rejects_concurrent_requests(self):
        entered, release = threading.Event(), threading.Event()
        def slow(*args):
            entered.set()
            release.wait(2)
            return {"text": "test"}
        with patch.object(bridge, "generate", side_effect=slow):
            thread = threading.Thread(target=lambda: self.request({"prompt": "test"}))
            thread.start()
            self.assertTrue(entered.wait(1))
            self.assertEqual(self.request({"prompt": "second"})[0], 429)
            release.set()
            thread.join(3)

    def test_disabled_by_default(self):
        other = bridge.server(bridge.Settings(), 0)
        thread = threading.Thread(target=other.serve_forever, daemon=True)
        thread.start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", other.server_port)
            c.request("POST", "/v1/generate", b'{}', {"Content-Type": "application/json"})
            r = c.getresponse(); self.assertEqual(r.status, 503); r.read(); c.close()
        finally:
            other.shutdown(); other.server_close(); thread.join(2)

    def test_activation_requires_credentials(self):
        with self.assertRaises(ValueError):
            bridge.Settings(enabled=True, token="short", model="x").validate()

    def test_upstream_contract(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        seen = []
        class Mock(BaseHTTPRequestHandler):
            def do_POST(self):
                seen.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
                b = json.dumps({"choices": [{"message": {"content": "bonjour", "tool_calls": ["ignored"]}}]}).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
            def log_message(self, *args): pass
        upstream = ThreadingHTTPServer(("127.0.0.1", 0), Mock)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True); thread.start()
        try:
            result = bridge.generate(bridge.Settings(upstream_port=upstream.server_port, model="test-only"), "test", 32)
            self.assertEqual(result["text"], "bonjour")
            self.assertFalse(result["tool_calls_executed"])
            self.assertEqual(seen[0][0], "/v1/chat/completions")
            self.assertEqual(seen[0][1]["model"], "test-only")
            self.assertNotIn("tools", seen[0][1])
        finally:
            upstream.shutdown(); upstream.server_close(); thread.join(2)


if __name__ == "__main__": unittest.main()
