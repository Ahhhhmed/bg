#!/usr/bin/env python3
"""
Dev server with HTTP Range (byte-serving) support: PMTiles reads the tiles
in byte ranges, and Python's stock http.server doesn't answer Range requests.

    python3 scripts/serve.py [port] [root]      # e.g. 8750 dist (the built site)
"""
import http.server
import os
import re
import sys


class RangeRequestHandler(http.server.SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()

        range_header = self.headers.get("Range")
        file_size = os.path.getsize(path)
        ctype = self.guess_type(path)

        if not range_header:
            f = open(path, "rb")
            self.send_response(200)
            self.send_header("Content-type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            return f

        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        start, end = m.groups()
        start = int(start) if start else 0
        end = int(end) if end else file_size - 1
        end = min(end, file_size - 1)
        length = end - start + 1

        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self._range_remaining = length
        return f

    def copyfile(self, source, outputfile):
        remaining = getattr(self, "_range_remaining", None)
        if remaining is None:
            return super().copyfile(source, outputfile)
        bufsize = 64 * 1024
        while remaining > 0:
            chunk = source.read(min(bufsize, remaining))
            if not chunk:
                break
            outputfile.write(chunk)
            remaining -= len(chunk)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    project = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.join(project, sys.argv[2]) if len(sys.argv) > 2 else project
    os.chdir(root)
    http.server.test(HandlerClass=RangeRequestHandler, port=port)
