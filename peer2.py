import socket
import threading
import os
import json
import uuid

HOST = "127.0.0.1"

class Peer:
    def __init__(self, port, neighbors):
        self.port = port
        self.neighbors = neighbors
        self.files_dir = f"peer_{port}_files"
        os.makedirs(self.files_dir, exist_ok=True)

    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, self.port))
        server.listen()
        print(f"🚀 [PEER {self.port}] Online. Storage: ./{self.files_dir}")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_client, args=(conn,)).start()

    def handle_client(self, conn):
        try:
            data = conn.recv(4096).decode()
            if not data: return
            request = json.loads(data)

            # 🔍 RECURSIVE SEARCH
            if request["type"] == "SEARCH":
                filename = request["file"]
                search_id = request.get("search_id", str(uuid.uuid4()))
                visited = request.get("visited", [])
                visited.append(self.port)

                # Check locally first
                if filename in os.listdir(self.files_dir):
                    response = {"status": "FOUND", "port": self.port}
                    conn.send(json.dumps(response).encode())
                else:
                    # Forward the request to neighbors not yet visited
                    found = False
                    for neighbor in self.neighbors:
                        if neighbor not in visited:
                            res = self.forward_search(neighbor, filename, visited, search_id)
                            if res and res["status"] == "FOUND":
                                conn.send(json.dumps(res).encode())
                                found = True
                                break
                    
                    if not found:
                        conn.send(json.dumps({"status": "NOT_FOUND"}).encode())

            elif request["type"] == "DOWNLOAD":
                filename = request["file"]
                path = os.path.join(self.files_dir, filename)
                if os.path.exists(path):
                    with open(path, "rb") as f:
                        conn.sendall(f.read()) # Send entire file

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            conn.close()

    def forward_search(self, neighbor_port, filename, visited, search_id):
        """Helper to ask neighbors for a file if I don't have it."""
        try:
            s = socket.socket()
            s.connect((HOST, neighbor_port))
            msg = {"type": "SEARCH", "file": filename, "visited": visited, "search_id": search_id}
            s.send(json.dumps(msg).encode())
            return json.loads(s.recv(1024).decode())
        except:
            return None

    def search(self, filename):
        print(f"🔎 Searching network for: {filename}...")
        # Start the recursive search with itself as the first visited node
        for neighbor in self.neighbors:
            res = self.forward_search(neighbor, filename, [self.port], str(uuid.uuid4()))
            if res and res["status"] == "FOUND":
                print(f"✅ Found at peer {res['port']}")
                return res["port"]
        
        print("❌ File not found in the network.")
        return None

    def download(self, filename, target_port):
        try:
            s = socket.socket()
            s.connect((HOST, target_port))
            s.send(json.dumps({"type": "DOWNLOAD", "file": filename}).encode())

            path = os.path.join(self.files_dir, filename)
            # Avoid overwrite logic
            if os.path.exists(path):
                path = os.path.join(self.files_dir, f"new_{filename}")

            with open(path, "wb") as f:
                while True:
                    chunk = s.recv(4096)
                    if not chunk: break
                    f.write(chunk)
            print(f"💾 Downloaded to {path}")
        except Exception as e:
            print(f"Download failed: {e}")
        finally:
            s.close()

if __name__ == "__main__":
    my_port = int(input("Enter your port: "))
    neighbors = list(map(int, input("Enter neighbor ports (space separated): ").split()))

    peer = Peer(my_port, neighbors)
    threading.Thread(target=peer.start_server, daemon=True).start()

    last_found_port = None
    while True:
        cmd = input("\n[1] Search [2] Download [3] Exit: ")
        if cmd == "1":
            fname = input("File name to search: ")
            last_found_port = peer.search(fname)
        elif cmd == "2":
            if last_found_port:
                fname = input("Confirm file name to download: ")
                peer.download(fname, last_found_port)
            else:
                print("Please search for a file first.")
        elif cmd == "3":
            break