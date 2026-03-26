"""
app.py — Ponto de entrada do Orquestrador como aplicativo desktop.

Sobe o servidor Flask central na porta 8080 e abre a interface web
do orquestrador via pywebview.
"""

import sys
import threading
import time

import webview
from main import app as flask_app

HOST = "127.0.0.1"
PORT = 8080
URL  = f"http://{HOST}:{PORT}"


def _run_server():
    """Inicia o Flask do Orquestrador em thread de fundo."""
    # use_reloader=False é essencial quando roda em uma thread paralela
    flask_app.run(host='0.0.0.0', port=PORT, use_reloader=False, threaded=True)


def _aguardar_servidor(timeout: int = 10) -> bool:
    """Aguarda o servidor responder antes de exibir a janela."""
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{URL}/status", timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    t = threading.Thread(target=_run_server, daemon=True)
    t.start()

    if not _aguardar_servidor():
        print("❌ Servidor do Orquestrador não respondeu a tempo.")
        sys.exit(1)

    window = webview.create_window(
        title="Manager RPA - Controle Central",
        url=URL,
        width=1200,
        height=720,
        min_size=(900, 600),
        resizable=True,
        text_select=False,
    )

    webview.start(debug=False)


if __name__ == "__main__":
    main()
