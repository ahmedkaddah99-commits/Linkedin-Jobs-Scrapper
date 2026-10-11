from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HOST = "0.0.0.0"
DEFAULT_PORT = 3000
DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"


class SpaStaticHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIST_DIR), **kwargs)

    def send_head(self):
        requested_path = Path(self.translate_path(self.path))
        if requested_path.is_file():
            return super().send_head()

        if requested_path.is_dir():
            index_path = requested_path / "index.html"
            if index_path.is_file():
                return super().send_head()

        return self._send_index_fallback()

    def _send_index_fallback(self):
        index_path = DIST_DIR / "index.html"
        if not index_path.is_file():
            self.send_error(500, f"Missing SPA entrypoint: {index_path}")
            return None

        self.path = "/index.html"
        return super().send_head()


def main() -> None:
    if not DIST_DIR.is_dir():
        raise SystemExit(f"Frontend build output not found: {DIST_DIR}. Run `npm --prefix frontend run build` first.")

    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    server = ThreadingHTTPServer((HOST, port), SpaStaticHandler)
    print(f"Serving frontend/dist with SPA fallback on http://{HOST}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
