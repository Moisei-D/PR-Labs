#!/usr/bin/env python3
"""The client and the provider of the coffee shop, in Python (bonus: two languages working together).

    python3 python/client.py client   [--host 127.0.0.1] [--port 5000]
    python3 python/client.py provider [--host 127.0.0.1] [--port 5000]

It speaks the same protocol as Client.cs: every message is one line of text that ends with '\\n'.
Only the socket module is used. Two threads: the main thread receives and shows the messages of the server,
a second thread reads the keyboard and sends what the user types.
"""
import argparse
import socket
import sys
import threading
import time

quitting = False


def read_keyboard(sock):
    global quitting
    for line in sys.stdin:
        line = line.strip()
        if line in ("quit", "exit"):
            break
        if line:
            try:
                sock.sendall((line + "\n").encode())
            except OSError:
                break   # the server is gone; the main thread notices the same in recv
    # the user has finished: close our direction only; the server closes its side and recv returns b""
    quitting = True
    try:
        sock.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["client", "provider"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect((args.host, args.port))
    except OSError as e:
        print(f"Cannot connect to {args.host}:{args.port}: {e}")
        return

    print(f"Connected to {args.host}:{args.port} as {'the provider' if args.role == 'provider' else 'a client'}.")
    print("Commands: menu | order croissant 2 tea 1 | deliver coffee 20 (provider) | quit")
    if args.role == "provider":
        sock.sendall(b"PROVIDER\n")

    # daemon: this thread does not keep the program alive when the main thread ends
    threading.Thread(target=read_keyboard, args=(sock,), daemon=True).start()

    data = b""   # the bytes of a message that has not arrived completely yet
    try:
        while True:
            received = sock.recv(4096)
            if not received:
                print("Bye." if quitting else "The server closed the connection.")
                break
            data += received
            while b"\n" in data:
                line, data = data.split(b"\n", 1)
                print(f"[{time.strftime('%H:%M:%S')}] {line.decode(errors='replace')}", flush=True)
    except OSError as e:
        print(f"The connection to the server was lost ({e}).")
    sock.close()


if __name__ == "__main__":
    main()
