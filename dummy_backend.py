import http.server
import time

class Dummy(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.send_header("Content-Length", "10")
        self.end_headers()
        self.wfile.write(b"0123456789")

if __name__ == "__main__":
    http.server.HTTPServer(("127.0.0.1", 8000), Dummy).serve_forever()
