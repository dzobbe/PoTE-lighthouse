#!/usr/bin/env python3
"""
Simple mock HTTP server for TEE attestation verification.
This server accepts POST requests to /attest/verify and always returns success.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import sys

class AttestationHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/attest/verify':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                # Parse the JSON request
                request_data = json.loads(post_data.decode('utf-8'))
                print(f"Received attestation request:")
                print(f"  Quote length: {len(request_data.get('quote', ''))}")
                print(f"  Version: {request_data.get('version', 'unknown')}")
                
                # Always return success for mock purposes
                response = {
                    "valid": True,
                    "mrenclave": "0" * 64,  # Mock MRENCLAVE
                    "mrsigner": "0" * 64,   # Mock MRSIGNER
                    "message": "Mock attestation verification successful"
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode('utf-8'))
                
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON: {e}")
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                error_response = {"error": "Invalid JSON", "valid": False}
                self.wfile.write(json.dumps(error_response).encode('utf-8'))
        else:
            self.send_response(404)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            error_response = {"error": "Not Found", "valid": False}
            self.wfile.write(json.dumps(error_response).encode('utf-8'))
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def run_server(port=3000):
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, AttestationHandler)
    print(f"Mock attestation server running on http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        httpd.shutdown()

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
    run_server(port)
