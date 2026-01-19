#!/usr/bin/env python3
from flask import Flask, jsonify
from waitress import serve
import subprocess
import threading
import requests
import signal
import sys
import os
import re

# ------------------------
# Flask app
# ------------------------
app = Flask(__name__)
latest_code = None
latest_code_lock = threading.Lock()

@app.route("/code", methods=["GET"])
def get_code():
    with latest_code_lock:
        return jsonify({"code": latest_code})

@app.route("/logout", methods=["POST"])
def logout():
    dc_result = send_zenith_command("dc")
    auth_clear_result = send_zenith_command("auth clear")

    return jsonify({
        "dc": dc_result,
        "auth_clear": auth_clear_result
    })

# ------------------------
# Zenith command sender (unchanged)
# ------------------------
def send_zenith_command(command: str) -> dict:
    url = "http://localhost:8080/command"
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": "zenith",
                "Content-Type": "application/json"
            },
            json={"command": command},
            timeout=3
        )
        return {
            "status": "success",
            "response_code": response.status_code,
            "response_body": response.json() if response.content else {}
        }
    except requests.RequestException as e:
        return {"status": "error", "message": str(e)}

# ------------------------
# Environment
# ------------------------
os.environ["PYTHONUNBUFFERED"] = "1"
proc = None

# ------------------------
# Signal handling
# ------------------------
def handle_sigterm(signum, frame):
    print("SIGTERM received → forwarding to Zenith", flush=True)
    if proc and proc.poll() is None:
        proc.send_signal(signal.SIGINT)

signal.signal(signal.SIGTERM, handle_sigterm)

# ------------------------
# Subprocess output reader
# ------------------------
DEVICE_CODE_REGEX = re.compile(
    r"Microsoft Device Code Login.*?"
    r"Login Here:\s+https://www\.microsoft\.com/link\?otc=\S+.*?"
    r"Code:\s+([A-Z0-9]+)",
    re.DOTALL
)

def read_proc_output(stream):
    global latest_code
    buffer = ""

    for line in iter(stream.readline, ''):
        sys.stdout.write(line)
        sys.stdout.flush()

        buffer += line
        if len(buffer) > 4096:
            buffer = buffer[-4096:]

        match = DEVICE_CODE_REGEX.search(buffer)
        if match:
            code = match.group(1)

            should_print = False
            with latest_code_lock:
                if latest_code != code:
                    latest_code = code
                    should_print = True

            if should_print:
                print(f"[ZenithProxy] New Microsoft device code detected: {code}", flush=True)

# ------------------------
# Start subprocess
# ------------------------
print("Starting ZenithProxy (runtime mode)...", flush=True)

proc = subprocess.Popen(
    ["/root/launch"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1
)

output_thread = threading.Thread(
    target=read_proc_output,
    args=(proc.stdout,),
    daemon=True
)
output_thread.start()

# ------------------------
# Command passthrough (unchanged)
# ------------------------
def send_command(cmd: str):
    if proc and proc.poll() is None:
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()

# ------------------------
# Start web server
# ------------------------
def start_web():
    serve(app, host="0.0.0.0", port=8081)

web_thread = threading.Thread(target=start_web, daemon=True)
web_thread.start()

# ------------------------
# Wait for process
# ------------------------
proc.wait()
