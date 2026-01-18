from flask import Flask, render_template, jsonify, request
from waitress import serve
import requests
import qrcode
import docker
import os

RESET = "\033[0m"
WHITE_FG = "\033[37m"
WHITE_BG = "\033[47m"
BLACK_FG = "\033[30m"
BLACK_BG = "\033[40m"

app = Flask(__name__)
client = docker.from_env()

ZENITH_IMAGE_PATH = "/root/Zenith/docker_image/zenith-proxy.tar"
ZENITH_IMAGE_NAME = "zenith-proxy:latest"

# Load image on startup if not present
def load_zenith_image():
    try:
        client.images.get(ZENITH_IMAGE_NAME)
    except docker.errors.ImageNotFound:
        print("Loading Zenith image...")
        client.images.load(open(ZENITH_IMAGE_PATH, "rb").read())

load_zenith_image()

# Helper functions
def list_containers():
    containers = client.containers.list(all=True, filters={"ancestor": ZENITH_IMAGE_NAME})
    return [
        {"id": c.id[:12], "name": c.name, "status": c.status}
        for c in containers
    ]

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
    c = client.containers.create(ZENITH_IMAGE_NAME, name=name, detach=True)
    return c.status

# Routes
@app.route("/")
def index():
    return render_template("index.html", containers=list_containers())

@app.route("/api/containers")
def api_list():
    return jsonify(list_containers())

@app.route("/api/containers/<name>/start", methods=["POST"])
def api_start(name):
    return jsonify({"status": start_container(name)})

@app.route("/api/containers/<name>/stop", methods=["POST"])
def api_stop(name):
    return jsonify({"status": stop_container(name)})

@app.route("/api/containers/<name>/restart", methods=["POST"])
def api_restart(name):
    return jsonify({"status": restart_container(name)})

@app.route("/api/containers/<name>/delete", methods=["POST"])
def api_delete(name):
    remove_container(name)
    return jsonify({"status": "deleted"})

@app.route("/api/containers/new", methods=["POST"])
def api_new():
    data = request.json
    name = data.get("name").replace(" ", "_")
    if not name:
        return jsonify({"error": "Name required"}), 400
    create_container(name)
    return jsonify({"status": "created"})

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
