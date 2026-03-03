# -------------------------------------------------------------------
# server.py — Lightweight HTTP server with JSON API routing.
#
# This replaces FastAPI for now (since we can't install packages).
# It provides a similar feel: you define routes with decorators,
# and requests/responses are automatically converted to/from JSON.
#
# HOW TO USE:
#   app = Router()
#
#   @app.get("/players")
#   def list_players(request):
#       return {"players": [...]}
#
#   @app.post("/users")
#   def create_user(request):
#       data = request["body"]  # parsed JSON body
#       return {"user": {...}}
#
# When you're ready to install FastAPI, porting is straightforward:
# the route handlers stay almost identical.
# -------------------------------------------------------------------

import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


class Router:
    """Simple route registry. Maps (method, path_pattern) -> handler function."""

    def __init__(self):
        self.routes = []  # list of (method, pattern, handler)

    def get(self, path):
        """Decorator to register a GET route."""
        def decorator(func):
            self.routes.append(("GET", path, func))
            return func
        return decorator

    def post(self, path):
        """Decorator to register a POST route."""
        def decorator(func):
            self.routes.append(("POST", path, func))
            return func
        return decorator

    def delete(self, path):
        """Decorator to register a DELETE route."""
        def decorator(func):
            self.routes.append(("DELETE", path, func))
            return func
        return decorator

    def match(self, method, path):
        """
        Find a matching route for the given method and path.

        Supports path parameters like /players/{player_id}.
        Returns (handler_function, path_params_dict) or (None, None).
        """
        for route_method, pattern, handler in self.routes:
            if route_method != method:
                continue

            params = self._match_pattern(pattern, path)
            if params is not None:
                return handler, params

        return None, None

    def _match_pattern(self, pattern, path):
        """
        Match a URL pattern against an actual path.

        /players/{player_id} matches /players/5 -> {"player_id": "5"}
        /players matches /players -> {}
        /players does NOT match /players/5
        """
        pattern_parts = pattern.strip("/").split("/")
        path_parts = path.strip("/").split("/")

        if len(pattern_parts) != len(path_parts):
            return None

        params = {}
        for pp, pathp in zip(pattern_parts, path_parts):
            if pp.startswith("{") and pp.endswith("}"):
                param_name = pp[1:-1]
                params[param_name] = pathp
            elif pp != pathp:
                return None

        return params


class APIHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler that routes requests to our API functions.

    Each request gets parsed into a dict:
        {
            "path_params": {"player_id": "5"},
            "query_params": {"search": "ohtani"},
            "body": {...},  # parsed JSON (POST requests)
        }
    """

    router = None  # Set by create_server()

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_OPTIONS(self):
        """Handle CORS preflight requests (needed for browser frontends)."""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def _handle_request(self, method):
        parsed = urlparse(self.path)
        path = parsed.path
        query_params = parse_qs(parsed.query)
        # Flatten single-value query params: {"q": ["test"]} -> {"q": "test"}
        query_params = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}

        handler, path_params = self.router.match(method, path)

        if handler is None:
            self._send_json(404, {"error": f"Not found: {method} {path}"})
            return

        # Parse JSON body for POST/PUT requests
        body = None
        if method in ("POST", "PUT", "PATCH"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                raw = self.rfile.read(content_length)
                try:
                    body = json.loads(raw)
                except json.JSONDecodeError:
                    self._send_json(400, {"error": "Invalid JSON in request body."})
                    return

        request = {
            "path_params": path_params,
            "query_params": query_params,
            "body": body or {},
        }

        try:
            result = handler(request)
            self._send_json(200, result)
        except ValueError as e:
            self._send_json(400, {"error": str(e)})
        except Exception as e:
            self._send_json(500, {"error": f"Internal server error: {str(e)}"})

    def _send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _set_cors_headers(self):
        """Allow requests from any origin (for local development)."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format, *args):
        """Override to make logs cleaner."""
        print(f"  {args[0]}")


def create_server(router: Router, host: str, port: int) -> HTTPServer:
    """Create an HTTP server with our router attached."""
    APIHandler.router = router
    server = HTTPServer((host, port), APIHandler)
    return server
