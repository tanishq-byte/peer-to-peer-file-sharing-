from flask import Flask, render_template, request, jsonify, send_from_directory
import socket
import threading
import os
import json

app = Flask(__name__)

# Global State
MY_PORT = None
NEIGHBORS = set()
FILES_DIR = ""

# --- P2P SERVER LOGIC ---

def start_p2p_server(port, directory):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", port + 1000))
    server.listen()
    print(f"[P2P] Listening on 127.0.0.1:{port + 1000}")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=handle_p2p_request, args=(conn, directory), daemon=True).start()

def handle_p2p_request(conn, directory):
    try:
        raw_data = b""
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            raw_data += chunk
            try:
                req = json.loads(raw_data.decode())
                break  # valid JSON received
            except json.JSONDecodeError:
                continue  # keep reading

        if not raw_data:
            return

        req = json.loads(raw_data.decode())

        if req["type"] == "SEARCH":
            filename = req["file"]
            visited = req.get("visited", [])
            if filename in os.listdir(directory):
                conn.send(json.dumps({"status": "FOUND", "port": MY_PORT}).encode())
            else:
                found_at = None
                visited.append(MY_PORT)
                for n in NEIGHBORS:
                    if n not in visited:
                        try:
                            s = socket.socket()
                            s.settimeout(1.5)
                            s.connect(("127.0.0.1", n + 1000))
                            req["visited"] = visited
                            s.send(json.dumps(req).encode())
                            res = json.loads(s.recv(4096).decode())
                            s.close()
                            if res["status"] == "FOUND":
                                found_at = res
                                break
                        except:
                            continue
                if found_at:
                    conn.send(json.dumps(found_at).encode())
                else:
                    conn.send(json.dumps({"status": "NOT_FOUND"}).encode())

        elif req["type"] == "DOWNLOAD":
            file_path = os.path.join(directory, req["file"])
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    conn.sendall(f.read())

        elif req["type"] == "GET_NEIGHBORS":
            conn.send(json.dumps({"neighbors": list(NEIGHBORS)}).encode())

    except Exception as e:
        print(f"[P2P] Error handling request: {e}")
    finally:
        conn.close()


# --- WEB UI ROUTES ---

@app.route('/')
def home():
    """Renders the landing/home page."""
    return render_template('home.html', port=MY_PORT)

@app.route('/dashboard')
def dashboard():
    """Renders the P2P dashboard."""
    files = os.listdir(FILES_DIR) if os.path.exists(FILES_DIR) else []
    return render_template('index.html', port=MY_PORT, files=files, neighbors=sorted(NEIGHBORS))


# --- API ENDPOINTS ---

@app.route('/add_peer', methods=['POST'])
def add_peer():
    peer = request.json.get('port')
    if peer is not None:
        peer = int(peer)
        if peer != MY_PORT:
            NEIGHBORS.add(peer)
            print(f"[PEER] Added peer :{peer}")
    return jsonify({"status": "success"})

@app.route('/remove_peer', methods=['POST'])
def remove_peer():
    peer = request.json.get('port')
    if peer is not None:
        peer = int(peer)
        NEIGHBORS.discard(peer)
        print(f"[PEER] Removed peer :{peer}")
    return jsonify({"status": "success"})

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file provided"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "Empty filename"}), 400
    save_path = os.path.join(FILES_DIR, file.filename)
    file.save(save_path)
    print(f"[UPLOAD] Saved: {file.filename}")
    return jsonify({"status": "success", "filename": file.filename})

@app.route('/search', methods=['POST'])
def search():
    filename = request.json.get('filename', '').strip()
    if not filename:
        return jsonify({"status": "NOT_FOUND"})

    # Check locally first
    if filename in os.listdir(FILES_DIR):
        return jsonify({"status": "FOUND", "peer": MY_PORT})

    # Search neighbors
    for n in NEIGHBORS:
        try:
            s = socket.socket()
            s.settimeout(2.0)
            s.connect(("127.0.0.1", n + 1000))
            query = {"type": "SEARCH", "file": filename, "visited": [MY_PORT]}
            s.send(json.dumps(query).encode())
            res = json.loads(s.recv(4096).decode())
            s.close()
            if res["status"] == "FOUND":
                return jsonify({"status": "FOUND", "peer": res["port"]})
        except:
            continue

    return jsonify({"status": "NOT_FOUND"})

@app.route('/download', methods=['POST'])
def download():
    data = request.json
    filename = data.get('filename', '').strip()
    target = int(data.get('peer'))

    if not filename:
        return jsonify({"status": "error", "message": "No filename"})

    # If the file is on this node, no need to download
    local_path = os.path.join(FILES_DIR, filename)
    if os.path.exists(local_path):
        return jsonify({"status": "success", "message": "Already have file"})

    try:
        s = socket.socket()
        s.settimeout(10.0)
        s.connect(("127.0.0.1", target + 1000))
        s.send(json.dumps({"type": "DOWNLOAD", "file": filename}).encode())
        data_received = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data_received += chunk
        s.close()

        if data_received:
            with open(local_path, "wb") as f:
                f.write(data_received)
            print(f"[DOWNLOAD] Saved '{filename}' from :{target}")
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "No data received"})
    except Exception as e:
        print(f"[DOWNLOAD] Error: {e}")
        return jsonify({"status": "error", "message": str(e)})

@app.route('/network_map')
def network_map():
    global_nodes = {}
    to_visit = [MY_PORT]
    visited = set()

    while to_visit:
        curr = to_visit.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
        try:
            if curr == MY_PORT:
                neighbors = list(NEIGHBORS)
            else:
                s = socket.socket()
                s.settimeout(1.0)
                s.connect(("127.0.0.1", curr + 1000))
                s.send(json.dumps({"type": "GET_NEIGHBORS"}).encode())
                res = json.loads(s.recv(4096).decode())
                s.close()
                neighbors = res.get("neighbors", [])
            global_nodes[str(curr)] = neighbors
            for n in neighbors:
                if n not in visited:
                    to_visit.append(n)
        except:
            global_nodes[str(curr)] = []

    return jsonify(global_nodes)

@app.route('/files')
def list_files():
    """Returns the list of files this node is sharing."""
    files = os.listdir(FILES_DIR) if os.path.exists(FILES_DIR) else []
    return jsonify({"files": files, "port": MY_PORT})


if __name__ == "__main__":
    MY_PORT = int(input("Enter Web Port: "))
    FILES_DIR = f"peer_{MY_PORT}_files"
    os.makedirs(FILES_DIR, exist_ok=True)

    p2p_thread = threading.Thread(target=start_p2p_server, args=(MY_PORT, FILES_DIR), daemon=True)
    p2p_thread.start()

    print(f"[WEB] Starting Flask on http://127.0.0.1:{MY_PORT}")
    app.run(port=MY_PORT, debug=False)