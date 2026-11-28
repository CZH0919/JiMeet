"""通过应用套接字验证指定主机的健康响应，失败时返回非零退出码。"""
import http.client
import json
import os
import socket
import sys


def main():
    host = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")[0].strip()
    path = os.environ.get("JIMEET_SOCKET", "/run/jimeet/web.sock")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(3)
        sock.connect(path)
        client = http.client.HTTPConnection(host)
        client.sock = sock
        client.request("GET", "/api/v1/healthz", headers={"X-Forwarded-Proto": "https"})
        with client.getresponse() as response:
            if response.status != 200:
                return 1
            payload = json.load(response)
            return int(payload.get("code") != "OK" or payload.get("data") != {"status": "ok"})


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, http.client.HTTPException):
        sys.exit(1)
