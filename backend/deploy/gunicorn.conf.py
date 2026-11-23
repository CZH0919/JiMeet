"""仅通过受限的 Unix 套接字接受同机 HTTPS 代理请求。"""
import os

bind = "unix:" + os.environ.get("JIMEET_SOCKET", "/run/jimeet/web.sock")
workers = 2
timeout = 30
umask = 0o007
control_socket_disable = True
