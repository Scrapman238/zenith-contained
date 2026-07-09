from flask import Flask, jsonify, request, send_from_directory, session, redirect, send_file
from datetime import datetime
from functools import wraps
from waitress import serve
import subprocess
import requests
import qrcode
import docker
import os
import re

def log_info(message):
    print(f"\033[92m[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \033[0m\033[34m[INFO]\033[0m {message}")

def log_warn(message):
    print(f"\033[93m[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \033[0m\033[33m[WARN]\033[0m {message}")

def log_error(message):
    print(f"\033[91m[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] \033[0m\033[31m[ERROR]\033[0m {message}")

def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org")
        response.raise_for_status()
        return response.text
    except requests.RequestException:
        return None

CONFIG_DIR = "/root/config"

CUSTOM_BG_PREFIX = "background."
DEFAULT_BG_PATH = os.path.join("static", "bg.png")
ALLOWED_BACKGROUND_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

os.makedirs(CONFIG_DIR, exist_ok=True)

PASSWORD_FILE = "/root/config/password.txt"
IPS_FILE = "/root/config/ips.txt"

if not os.path.exists(PASSWORD_FILE):
    print(f"[ERROR] Password file '{PASSWORD_FILE}' not found. Please create it with the root password.")
    exit(1)

with open(PASSWORD_FILE, "r") as f:
    ROOT_PASSWORD = f.read().strip()

PRIMARY_IP = get_public_ip()
EXTRA_IPS = []

if os.path.exists(IPS_FILE):
    with open(IPS_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                EXTRA_IPS.append(line)
else:
    print(f"[WARN] IPs file '{IPS_FILE}' not found. No extra IPs loaded.")
    print("[INFO] Creating blank ips.txt file for you to edit.")
    with open(IPS_FILE, "w") as f:
        f.write("# Add extra IPs here, one per line.\n")

print(f"[INFO] Primary IP: {PRIMARY_IP}")
print(f"[INFO] Extra IPs: {EXTRA_IPS}")

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
        log_info(f"Zenith image '{ZENITH_IMAGE_NAME}' already present")
    except docker.errors.ImageNotFound:
        log_info("Loading Zenith image...")
        client.images.load(open(ZENITH_IMAGE_PATH, "rb").read())
        log_info("Zenith image loaded")

load_zenith_image()

# --- Helper functions ---
def list_containers():
    containers = client.containers.list(
        all=True,
        filters={"ancestor": ZENITH_IMAGE_NAME}
    )

    log_info(f"Found {len(containers)} containers for image {ZENITH_IMAGE_NAME}")

    result = []

    for c in sorted(containers, key=lambda x: x.name):
        instance_number = int(c.name.replace("instance_", ""))
        port = instance_to_port(8080, instance_number, ports_per_instance)

        outbound_ip = get_instance_outbound_ip(instance_number)

        result.append({
            "id": c.id[:12],
            "name": c.name,
            "instance": instance_number,
            "status": c.status.title(),
            "port": port,
            "url": f"http://localhost:{port}",
            "ip": outbound_ip,  # ✅ NEW FIELD
        })

    return sorted(result, key=lambda x: x["instance"])

def get_instance_outbound_ip(instance_number):
    if instance_number == 1:
        return PRIMARY_IP
    index = instance_number - 2
    if 0 <= index < len(EXTRA_IPS):
        return EXTRA_IPS[index]
    return None

def instance_to_port(base_port, instance_number, ports_per_instance=1):
    return base_port + (instance_number - 1) * ports_per_instance

def get_next_instance_name():
    existing = [int(c["name"].replace("instance_", "")) for c in list_containers()]
    i = 1
    while i in existing:
        i += 1
    return f"instance_{i}"

def get_next_instance_name():
    existing = sorted(
        int(c["name"].replace("instance_", ""))
        for c in list_containers()
    )

    i = 1
    while i in existing:
        i += 1

    if i == 1:
        return "instance_1"

    if i - 2 >= len(EXTRA_IPS):
        return None

    return f"instance_{i}"

def set_container_snat(container_name, host_ip):
    container = client.containers.get(container_name)

    container.reload()

    container_ip = next(
        iter(
            container.attrs["NetworkSettings"]["Networks"].values()
        )
    )["IPAddress"]

    log_info(f"Adding SNAT {container_ip} → {host_ip}")

    try:
        subprocess.run([
            "iptables",
            "-t", "nat",
            "-C", "POSTROUTING",
            "-s", container_ip,
            "-j", "SNAT",
            "--to-source", host_ip
        ], check=True)

    except subprocess.CalledProcessError:
        subprocess.run([
            "iptables",
            "-t", "nat",
            "-I", "POSTROUTING", "1",
            "-s", container_ip,
            "-j", "SNAT",
            "--to-source", host_ip
        ], check=True)

        log_info("SNAT rule added")

def restore_all_snat():
    log_info("Restoring SNAT rules...")

    containers = client.containers.list(
        all=True,
        filters={"ancestor": ZENITH_IMAGE_NAME}
    )

    for container in containers:
        try:
            instance_number = int(container.name.replace("instance_", ""))
        except ValueError:
            continue

        outbound_ip = get_instance_outbound_ip(instance_number)

        if not outbound_ip:
            log_warn(f"{container.name}: no outbound IP assigned")
            continue

        container.reload()

        networks = container.attrs["NetworkSettings"]["Networks"]

        if not networks:
            log_warn(f"{container.name}: no network found")
            continue

        container_ip = next(iter(networks.values()))["IPAddress"]

        if not container_ip:
            log_warn(f"{container.name}: no container IP")
            continue

        log_info(f"Restoring {container.name}: {container_ip} → {outbound_ip}")

        try:
            subprocess.run([
                "iptables",
                "-t", "nat",
                "-C", "POSTROUTING",
                "-s", container_ip,
                "-j", "SNAT",
                "--to-source", outbound_ip
            ], check=True)

            log_info(f"{container.name}: rule already exists")

        except subprocess.CalledProcessError:
            subprocess.run([
                "iptables",
                "-t", "nat",
                "-I", "POSTROUTING", "1",
                "-s", container_ip,
                "-j", "SNAT",
                "--to-source", outbound_ip
            ], check=True)

            log_info(f"{container.name}: SNAT restored")

def start_container(name):
    log_info(f"Starting container {name}")
    c = client.containers.get(name)
    c.start()
    status = c.status
    log_info(f"Container {name} status after start: {status}")
    return status

def stop_container(name):
    log_info(f"Stopping container {name}")
    c = client.containers.get(name)
    c.stop()
    status = c.status
    log_info(f"Container {name} status after stop: {status}")
    return status

def restart_container(name):
    log_info(f"Restarting container {name}")
    c = client.containers.get(name)
    c.restart()
    status = c.status
    log_info(f"Container {name} status after restart: {status}")
    return status

def remove_container(name):
    log_info(f"Removing container {name}")
    c = client.containers.get(name)
    c.remove(force=True)
    log_info(f"Container {name} removed")
    return True

def create_container(name):
    instance_number = int(name.replace("instance_", ""))

    outbound_ip = get_instance_outbound_ip(instance_number)

    port = instance_to_port(8080, instance_number, ports_per_instance)
    proxy_port = instance_to_port(6000, instance_number, 1)

    c = client.containers.create(
        ZENITH_IMAGE_NAME,
        name=name,
        detach=True,
        restart_policy={
            "Name": "unless-stopped"
        },
        ports={
            "8080/tcp": ("127.0.0.1", port),
            "8081/tcp": ("127.0.0.1", port + 1),
            "3000/tcp": ("0.0.0.0", proxy_port),
        },
    )

    c.start()

    log_info(f"SNAT: {name} outbound → {outbound_ip}")
    log_info(f"Published ports for {name}: 8080→{port}, 8081→{port+1}, proxy→{proxy_port}")

    set_container_snat(name, outbound_ip)
    log_info(f"Applied SNAT for {name} → {outbound_ip}")

    return c.status

# --- API routes ---
@app.route("/api/containers")
@login_required
def api_list():
    log_info("API: list containers")
    return jsonify(list_containers())

@app.route("/api/containers/add", methods=["POST"])
@login_required
def api_add():
    name = get_next_instance_name()
    if not name:
        log_warn("API: add container failed — no free IPs available")
        return jsonify({
            "status": "error",
            "message": "No free IPs available"
        }), 400

    log_info(f"API: creating container {name}")
    create_container(name)
    return jsonify({"status": "created", "name": name})

@app.route("/api/containers/<name>/start", methods=["POST"])
@login_required
def api_start(name):
    log_info(f"API: start {name}")
    return jsonify({"status": start_container(name)})

@app.route("/api/containers/<name>/stop", methods=["POST"])
@login_required
def api_stop(name):
    log_info(f"API: stop {name}")
    return jsonify({"status": stop_container(name)})

@app.route("/api/containers/<name>/restart", methods=["POST"])
@login_required
def api_restart(name):
    log_info(f"API: restart {name}")
    return jsonify({"status": restart_container(name)})

@app.route("/api/containers/<name>/delete", methods=["POST"])
@login_required
def api_delete(name):
    log_info(f"API: delete {name}")
    remove_container(name)
    return jsonify({"status": "deleted"})

@app.route("/api/containers/<name>/update-discord", methods=["POST"])
@login_required
def update_discord(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(8080, instance_number, ports_per_instance) + 1
    url = f"http://localhost:{port}/update-discord"

    try:
        response = requests.post(url, data=request.form)
        if response.status_code != 200:
            print(f"[WARN] Container responded with {response.status_code}")
    except requests.RequestException as e:
        print(f"[ERROR] Could not reach container: {e}")

    return redirect("/")

@app.route("/api/containers/<name>/zenith-status", methods=["GET"])
@login_required
def api_status(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(8080, instance_number, ports_per_instance)
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

    port = instance_to_port(8080, instance_number, ports_per_instance)
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

@app.route("/api/containers/<name>/send_super_command", methods=["POST"])
@login_required
def api_send_super_command(name):
    data = request.get_json()
    if not data or "command" not in data:
        return jsonify({"error": "Missing 'command' in request body"}), 400

    command = data["command"]

    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(8080, instance_number, ports_per_instance) + 1
    url = f"http://localhost:{port}/super_command"

    try:
        response = requests.post(
            url,
            headers={
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
        if password == ROOT_PASSWORD:
            session["authenticated"] = True
            return redirect("/")
        return "Invalid password", 401

    return send_from_directory("static", "login.html")

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect("/login")

# --- Serve static files ---
@app.route("/<path:path>")
@login_required
def static_files(path):
    return send_from_directory("static", path)

@app.route("/static/mojangles.otf", methods=["GET"])
def mojangles_font():
    return send_from_directory("static", "mojangles.otf")

@app.route("/api/ui/background/change", methods=["POST"])
@login_required
def change_background():
    if "background" not in request.files:
        log_warn("API: background change attempted without file")
        return jsonify({"error": "No file provided"}), 400

    file = request.files["background"]

    if file.filename == "":
        log_warn("API: background change attempted with empty filename")
        return jsonify({"error": "Empty filename"}), 400

    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_BACKGROUND_EXTENSIONS:
        log_warn(f"API: background change invalid extension: {ext}")
        return jsonify({"error": "Invalid file type"}), 400

    # Remove any existing custom background
    for f in os.listdir(CONFIG_DIR):
        if f.startswith(CUSTOM_BG_PREFIX):
            os.remove(os.path.join(CONFIG_DIR, f))

    path = os.path.join(CONFIG_DIR, f"{CUSTOM_BG_PREFIX}{ext}")
    file.save(path)

    log_info(f"Background changed, saved to {path}")

    return jsonify({"status": "ok"})

@app.route("/api/ui/background/reset", methods=["POST"])
@login_required
def reset_background():
    for f in os.listdir(CONFIG_DIR):
        if f.startswith(CUSTOM_BG_PREFIX):
            os.remove(os.path.join(CONFIG_DIR, f))

    log_info("Background reset to default")
    return jsonify({"status": "reset", "background": "default"})

@app.route("/background", methods=["GET"])
@login_required
def serve_background():
    # Serve custom background if present
    for f in os.listdir(CONFIG_DIR):
        if f.startswith(CUSTOM_BG_PREFIX):
            return send_file(
                os.path.join(CONFIG_DIR, f),
                conditional=True
            )

    return send_file(
        DEFAULT_BG_PATH,
        conditional=True
    )

@app.route("/api/containers/<name>/code", methods=["GET"])
@login_required
def api_get_code(name):
    try:
        instance_number = int(name.replace("instance_", ""))
    except ValueError:
        return jsonify({"error": "Invalid container name"}), 400

    port = instance_to_port(8080, instance_number, ports_per_instance) + 1
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

    port = instance_to_port(8080, instance_number, ports_per_instance) + 1
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

def update_netplan(extra_ips):
    if not extra_ips:
        log_info("No extra IPs → netplan unchanged")
        return

    iface = None
    for line in os.popen("ip -o link show").read().splitlines():
        name = line.split(":")[1].strip()
        if name != "lo":
            iface = name
            break

    if not iface:
        log_error("Could not detect interface for netplan update")
        return

    addresses = "\n".join(f"           - {ip}/32" for ip in extra_ips)

    netplan = f"""network:
   version: 2
   ethernets:
       {iface}:
           dhcp4: true
           addresses:
{addresses}
"""

    with open("/etc/netplan/51-cloud-init.yaml", "w") as f:
        f.write(netplan)

    subprocess.run(["netplan", "apply"], check=True)

    log_info("Netplan updated")

if __name__ == "__main__":
    public_ip = get_public_ip()
    if not public_ip:
        log_error("Could not determine public IP.")
        public_ip = "0.0.0.0"

    os.system("clear")
    print("########################")
    print("# Zenith Manager Setup #")
    print("########################")
    print(f"Open for setup: http://{public_ip}:8000/\n")
    if public_ip != "0.0.0.0":
        print_qr_ascii(f"http://{public_ip}:8000/")

    update_netplan(EXTRA_IPS)
    restore_all_snat()

    log_info(f"Starting server on 0.0.0.0:8000 (public ip {public_ip})")
    serve(app, host="0.0.0.0", port=8000)
