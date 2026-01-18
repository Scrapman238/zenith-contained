from waitress import serve
from flask import Flask, render_template, jsonify, request
import docker
import os

app = Flask(__name__)
client = docker.from_env()

ZENITH_IMAGE_PATH = "/root/docker_image/zenith-proxy.tar.gz"
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
    name = data.get("name")
    if not name:
        return jsonify({"error": "Name required"}), 400
    create_container(name)
    return jsonify({"status": "created"})

if __name__ == "__main__":
    os.system("clear")
    print("Zenith Proxy Manager running on http://0.0.0.0:8080")
    serve(app, host="0.0.0.0", port=8080)
