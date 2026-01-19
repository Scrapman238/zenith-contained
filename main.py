from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
from functools import wraps
from waitress import serve
import subprocess
import requests
import qrcode
import docker
import os
import re

def verify_root_password(password: str) -> bool:
    try:
        p = subprocess.run(
            ["sudo", "-k", "-S", "true"],
            input=password + "\n",
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return p.returncode == 0
    except Exception:
        return False

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated

def parse_zenith_status(text: str) -> dict:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    result = {}

    header = lines.pop(0)
    m = re.match(r"ZenithProxy\s+(.+?)\s+-\s+(.+)", header)
    if m:
        result["Version"] = m.group(1)
        result["Account"] = m.group(2)

    i = 0
    while i < len(lines):
        key = lines[i]

        if key == "2b2t Queue":
            result[key] = {
                "Priority": lines[i + 1].split(":", 1)[1].strip(),
                "Regular": lines[i + 2].split(":", 1)[1].strip(),
            }
            i += 3
            continue

        if key == "Coordinates":
            result[key] = lines[i + 1]
            i += 2
            continue

        if i + 1 < len(lines):
            result[key] = lines[i + 1]
            i += 2
        else:
            i += 1

    return result

RESET = "\033[0m"
WHITE_FG = "\033[37m"
WHITE_BG = "\033[47m"
BLACK_FG = "\033[30m"
BLACK_BG = "\033[40m"

app = Flask(__name__, static_folder="static")
app.secret_key = os.urandom(32)
client = docker.from_env()

ports_per_instance = 2

# ZENITH_IMAGE_PATH = "/root/Zenith/docker_image/zenith-proxy.tar"
ZENITH_IMAGE_PATH = "docker_image/zenith-proxy.tar"
ZENITH_IMAGE_NAME = "zenith-proxy:latest"

# --- Docker image loading ---
def load_zenith_image():
    try:
        client.images.get(ZENITH_IMAGE_NAME)
    except docker.errors.ImageNotFound:
        print("Loading Zenith image...")
        client.images.load(open(ZENITH_IMAGE_PATH, "rb").read())

load_zenith_image()

# --- Helper functions ---
def list_containers():
    containers = client.containers.list(
        all=True,
        filters={"ancestor": ZENITH_IMAGE_NAME}
    )

    result = []

    for i, c in enumerate(sorted(containers, key=lambda x: x.name)):
        instance_number = int(c.name.replace("instance_", ""))

        port = instance_to_port(instance_number, ports_per_instance)

        result.append({
            "id": c.id[:12],
            "name": c.name,
            "instance": instance_number,
            "status": c.status.title(),
            "port": port,
            "url": f"http://localhost:{port}",
        })

    return sorted(result, key=lambda x: x["instance"])

def instance_to_port(instance_number, ports_per_instance=1):
    BASE_PORT = 9000
    return BASE_PORT + (instance_number - 1) * ports_per_instance

def get_next_instance_name():
    existing = [int(c["name"].replace("instance_", "")) for c in list_containers()]
    i = 1
    while i in existing:
        i += 1
    return f"instance_{i}"

def start_container(name):
    c = client.containers.get(name)
    c.start()
    return c.status

def stop_container(name):
    c = client.containers.get(name)
    c.stop()
    return c.status

def restart_container(name):
    c = client.containers.get(name)
    c.restart()
    return c.status

def remove_container(name):
    c = client.containers.get(name)
    c.remove(force=True)
    return True

def create_container(name):
    instance_number = int(name.replace("instance_", ""))
    port = instance_to_port(instance_number, ports_per_instance)

    c = client.containers.create(
        ZENITH_IMAGE_NAME,
        name=name,
        detach=True,
        ports={
            "8080/tcp": port,
            "8081/tcp": port + 1,
        },
    )
    return c.status

# --- API routes ---
@app.route("/api/containers")
@login_required
def api_list():
    return jsonify(list_containers())

@app.route("/api/containers/add", methods=["POST"])
@login_required
def api_add():
    name = get_next_instance_name()
    create_container(name)
    return jsonify({"status": "created", "name": name})

@app.route("/api/containers/<name>/start", methods=["POST"])
@login_required
def api_start(name):
    return jsonify({"status": start_container(name)})

@app.route("/api/containers/<name>/stop", methods=["POST"])
@login_required
def api_stop(name):
    return jsonify({"status": stop_container(name)})

@app.route("/api/containers/<name>/restart", methods=["POST"])
@login_required
def api_restart(name):
    return jsonify({"status": restart_container(name)})

@app.route("/api/containers/<name>/delete", methods=["POST"])
@login_required
def api_delete(name):
    remove_container(name)
    return jsonify({"status": "deleted"})

@app.route("/api/containers/<name>/zenith-status", methods=["GET"])
@login_required
def api_status(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(instance_number, ports_per_instance)
    url = f"http://localhost:{port}/command"

    try:
        response = requests.post(
            url,
            headers={
                "Authorization": "zenith",
                "Content-Type": "application/json"
            },
            json={"command": "status"},
            timeout=3
        )
        return jsonify({
            "status": "success",
            "response_code": response.status_code,
            "response_body": parse_zenith_status(response.json().get("embed", "")) if response.content else {}
        })
    except requests.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/containers/<name>/send_command", methods=["POST"])
@login_required
def api_send_command(name):
    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "Missing 'command' in request body"}), 400

    command = data["command"]

    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(instance_number, ports_per_instance)
    url = f"http://localhost:{port}/command"

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
        return jsonify({
            "status": "success",
            "response_code": response.status_code,
            "response_body": response.json() if response.content else {}
        })
    except requests.RequestException as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/")
@login_required
def index():
    return send_from_directory("static", "index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if verify_root_password(password):
            session["authenticated"] = True
            return redirect("/")
        return "Invalid password", 401

    return """
    <html>
        <body>
            <h2>Zenith Manager Login</h2>
            <form method="POST">
                <input type="password" name="password" placeholder="Root password" />
                <button type="submit">Login</button>
            </form>
        </body>
    </html>
    """

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")

# --- Serve static files ---
@app.route("/<path:path>")
@login_required
def static_files(path):
    return send_from_directory("static", path)

@app.route("/api/containers/<name>/code", methods=["GET"])
@login_required
def api_get_code(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(instance_number, ports_per_instance) + 1
    url = f"http://localhost:{port}/code"

    try:
        r = requests.get(url, timeout=2)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route("/api/containers/<name>/logout", methods=["POST"])
@login_required
def api_container_logout(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(instance_number, ports_per_instance) + 1
    url = f"http://localhost:{port}/logout"

    try:
        r = requests.post(url, timeout=5)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.RequestException as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org")
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None

def print_qr_ascii(data):
    qr = qrcode.QRCode(border=2)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    if len(matrix) % 2 != 0:
        matrix.append([False]*len(matrix[0]))

    for y in range(0, len(matrix), 2):
        line = ""
        for x in range(len(matrix[0])):
            upper = matrix[y][x]
            lower = matrix[y+1][x]

            fg = WHITE_FG if upper else BLACK_FG
            bg = WHITE_BG if lower else BLACK_BG

            line += f"{fg}{bg}▀{RESET}"
        print(line)

if __name__ == "__main__":
    public_ip = get_public_ip()
    if not public_ip:
        print("[ERROR] Could not determine public IP.")
        public_ip = "0.0.0.0"

    os.system("clear")
    print("########################")
    print("# Zenith Manager Setup #")
    print("########################")
    print(f"Open for setup: http://{public_ip}:8080/\n")
    if public_ip != "0.0.0.0":
        print_qr_ascii(f"http://{public_ip}:8080/")

    serve(app, host="0.0.0.0", port=8080)
