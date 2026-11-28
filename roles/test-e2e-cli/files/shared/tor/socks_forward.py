"""A local TCP port that forwards every connection through a SOCKS5 proxy to one onion service."""

import contextlib
import socket
import sys
import threading


def _recvall(sock, size):
    buf = b""
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise OSError("short read from SOCKS")
        buf += chunk
    return buf


def _socks_connect(proxy_host, proxy_port, onion, port):
    sock = socket.create_connection((proxy_host, proxy_port), timeout=120)
    sock.settimeout(120)
    sock.sendall(b"\x05\x01\x00")
    if _recvall(sock, 2) != b"\x05\x00":
        raise OSError("SOCKS5 no-auth rejected")
    host = onion.encode()
    sock.sendall(
        b"\x05\x01\x00\x03" + bytes([len(host)]) + host + port.to_bytes(2, "big")
    )
    hdr = _recvall(sock, 4)
    if hdr[1] != 0:
        raise OSError(f"SOCKS5 CONNECT failed rep={hdr[1]}")
    atyp = hdr[3]
    if atyp == 1:
        _recvall(sock, 4)
    elif atyp == 3:
        _recvall(sock, _recvall(sock, 1)[0])
    elif atyp == 4:
        _recvall(sock, 16)
    _recvall(sock, 2)
    sock.settimeout(None)
    return sock


def _pipe(source, target):
    try:
        with contextlib.suppress(OSError):
            while True:
                data = source.recv(65536)
                if not data:
                    break
                target.sendall(data)
    finally:
        with contextlib.suppress(OSError):
            target.shutdown(socket.SHUT_WR)


def start_forward(proxy, onion, port):
    """Serve 127.0.0.1:<returned port> in daemon threads, each connection tunnelled to the onion.

    Args:
        proxy: SOCKS5 proxy as ``host:port``.
        onion: onion host the proxy connects to.
        port: port of the onion service.

    Returns:
        The local port the forward listens on.
    """
    proxy_host, proxy_port = proxy.rsplit(":", 1)

    def handle(conn):
        try:
            upstream = _socks_connect(proxy_host, int(proxy_port), onion, port)
        except OSError as exc:
            print(f"socks connect failed: {exc}", file=sys.stderr)
            conn.close()
            return
        threading.Thread(target=_pipe, args=(conn, upstream), daemon=True).start()
        _pipe(upstream, conn)

    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(4)

    def serve():
        while True:
            try:
                conn, _ = listener.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=serve, daemon=True).start()
    return listener.getsockname()[1]
