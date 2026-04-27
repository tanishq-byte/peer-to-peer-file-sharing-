import socket
import threading
import os
import json

HOST = "127.0.0.1"

class Peer:
    def __init__(self, port, neighbors):
        self.port = port
        self.neighbors = neighbors

    # 🟢 START SERVER
    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, self.port))
        server.listen()

        print(f"[PEER {self.port}] Running...")

        while True:
            conn, addr = server.accept()
            threading.Thread(target=self.handle_client, args=(conn,)).start()

    # 🧠 HANDLE REQUESTS
    def handle_client(self, conn):
        try:
            data = conn.recv(1024).decode()
            request = json.loads(data)

            # 🔍 SEARCH
            if request["type"] == "SEARCH":
                filename = request["file"]

                if filename in os.listdir("files"):
                    response = {"status": "FOUND", "port": self.port}
                else:
                    response = {"status": "NOT_FOUND"}

                conn.send(json.dumps(response).encode())

            # 📥 DOWNLOAD
            elif request["type"] == "DOWNLOAD":
                filename = request["file"]

                if filename in os.listdir("files"):
                    with open(f"files/{filename}", "rb") as f:
                        while True:
                            chunk = f.read(1024)
                            if not chunk:
                                break
                            conn.send(chunk)

        except Exception as e:
            print("Error:", e)

        conn.close()

    # 🔍 SEARCH NETWORK
    def search(self, filename):
        print(f"Searching for {filename}...")

        for neighbor in self.neighbors:
            try:
                s = socket.socket()
                s.connect((HOST, neighbor))

                msg = {"type": "SEARCH", "file": filename}
                s.send(json.dumps(msg).encode())

                response = json.loads(s.recv(1024).decode())

                if response["status"] == "FOUND":
                    print(f"Found at peer {response['port']}")
                    s.close()
                    return response["port"]

                s.close()
            except:
                pass

        print("File not found")
        return None

    # 📥 DOWNLOAD FILE
    def download(self, filename, port):
        s = socket.socket()
        s.connect((HOST, port))

        msg = {"type": "DOWNLOAD", "file": filename}
        s.send(json.dumps(msg).encode())

        os.makedirs("files", exist_ok=True)

        # 🚫 avoid overwrite
        path = f"files/{filename}"
        if os.path.exists(path):
            base, ext = os.path.splitext(filename)
            filename = base + "_copy" + ext
            path = f"files/{filename}"

        with open(path, "wb") as f:
            while True:
                data = s.recv(1024)
                if not data:
                    break
                f.write(data)

        print(f"Downloaded {filename}")
        s.close()


# 🚀 MAIN
if __name__ == "__main__":
    port = int(input("Enter peer port: "))
    neighbors = list(map(int, input("Enter neighbor ports: ").split()))

    peer = Peer(port, neighbors)

    threading.Thread(target=peer.start_server, daemon=True).start()

    found_port = None

    while True:
        print("\n1. Search file")
        print("2. Download file")

        choice = input("> ")

        if choice == "1":
            filename = input("File name: ")
            found_port = peer.search(filename)

        elif choice == "2":
            if found_port:
                filename = input("File name: ")
                peer.download(filename, found_port)
            else:
                print("Search first.")