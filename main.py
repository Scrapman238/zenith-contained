import requests
from flask import Flask
from waitress import serve
import qrcode

# ANSI colors
RESET = "\033[0m"
WHITE_FG = "\033[37m"
WHITE_BG = "\033[47m"
BLACK_FG = "\033[30m"
BLACK_BG = "\033[40m"

# Flask app
app = Flask(__name__)

@app.route("/")
def index():
    return "This is a simple test page!"

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
    matrix = qr.get_matrix()  # True = black, False = white

    # Pad if odd number of rows
    if len(matrix) % 2 != 0:
        matrix.append([False]*len(matrix[0]))

    for y in range(0, len(matrix), 2):
        line = ""
        for x in range(len(matrix[0])):
            upper = matrix[y][x]      # top pixel
            lower = matrix[y+1][x]    # bottom pixel

            # Use built-in colors
            fg = WHITE_FG if upper else BLACK_FG
            bg = WHITE_BG if lower else BLACK_BG

            line += f"{fg}{bg}▀{RESET}"
        print(line)

if __name__ == "__main__":
    public_ip = get_public_ip()
    if not public_ip:
        print("Could not determine public IP.")
        exit(1)

    print("########################")
    print("# Zenith Manager Setup #")
    print("########################")
    print(f"Open for setup: http://{public_ip}:8080/\n")
    print_qr_ascii(f"http://{public_ip}:8080/")

    serve(app, host="0.0.0.0", port=8080)
