#!/usr/bin/env python3
"""Print this machine's primary LAN IPv4 and the broker URI to type into the board."""
import socket


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))   # no packet is sent; just picks the default route
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ip = lan_ip()
    print("LAN IP        :", ip)
    print("dashboard     : http://%s:8081/dashboard.html" % ip)
    print("broker (board): mqtt://%s:1883" % ip)
