"""A local HubSpot-style contacts API. Planted defects simulate real sync bugs."""
import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import config

CONTACTS = "/crm/v3/objects/contacts"


def make_server(host: str, port: int, defects: bool = True) -> ThreadingHTTPServer:
    store = {}                       # hubspot_id -> properties
    state = {"next_id": 1000}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, body):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _error(self, status, message):
            self._send(status, {"status": "error", "message": message})

        def do_POST(self):
            if urlparse(self.path).path != CONTACTS:
                return self._error(404, "Resource not found")
            length = int(self.headers.get("Content-Length", 0))
            try:
                props = json.loads(self.rfile.read(length))["properties"]
                lead_id = int(props.get("lead_id", 0))
            except (ValueError, KeyError, TypeError, AttributeError):
                return self._error(400, "Invalid request body")
            if not props.get("email"):
                return self._error(400, "email is required")

            with lock:
                if any(c["email"] == props["email"] for c in store.values()):
                    return self._error(409, "Contact already exists")

                stored = dict(props)
                if defects:
                    # DEFECT 2: company silently cut to 30 characters
                    if len(stored.get("company", "")) > 30:
                        stored["company"] = stored["company"][:30]
                    # DEFECT 3: phone numbers with an extension are wiped
                    if "x" in stored.get("phone", ""):
                        stored["phone"] = ""

                hs_id = str(state["next_id"])
                state["next_id"] += 1
                # DEFECT 1: answers 201 but never stores every 97th lead
                if not (defects and lead_id % 97 == 0):
                    store[hs_id] = stored
            self._send(201, {"id": hs_id, "properties": stored})

        def do_GET(self):
            url = urlparse(self.path)
            if url.path == CONTACTS:
                query = parse_qs(url.query)
                try:
                    limit = int(query.get("limit", ["100"])[0])
                    after = int(query.get("after", ["0"])[0])
                except ValueError:
                    return self._error(400, "limit and after must be integers")
                with lock:
                    ids = sorted(int(i) for i in store if int(i) > after)
                    page = ids[:limit]
                    results = [{"id": str(i), "properties": store[str(i)]} for i in page]
                body = {"results": results}
                if len(ids) > limit:
                    body["paging"] = {"next": {"after": str(page[-1])}}
                return self._send(200, body)

            match = re.fullmatch(CONTACTS + r"/(\d+)", url.path)
            if match:
                with lock:
                    props = store.get(match.group(1))
                if props is None:
                    return self._error(404, "Resource not found")
                return self._send(200, {"id": match.group(1), "properties": props})
            self._error(404, "Resource not found")

        def log_message(self, *args):  # keep the console quiet
            pass

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-defects", action="store_true", help="run a healthy API")
    args = parser.parse_args()
    server = make_server(config.HOST, config.PORT, defects=not args.no_defects)
    mode = "healthy" if args.no_defects else "with planted defects"
    print(f"Mock HubSpot API running at {config.BASE_URL} ({mode}). Ctrl+C to stop.")
    server.serve_forever()