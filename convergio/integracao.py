"""Integração com os navegadores e instância única.

O Convergio escuta em 127.0.0.1:PORTA (só na própria máquina). A extensão do navegador envia os downloads
para /baixar; uma segunda cópia do programa (atalho, protocolo convergio:) usa /abrir para entregar os
links à cópia que já está aberta.

Segurança: páginas da web não conseguem usar esta porta. Os pedidos precisam do cabeçalho X-Convergio
(o que obriga o navegador a fazer uma verificação CORS que este servidor nunca aprova) e, quando trazem
Origin, ela tem que ser de uma extensão (chrome-extension://, moz-extension://, extension://).
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QObject, Signal

from . import APP_NAME, __version__

PORTA = 47851
ORIGENS_EXTENSAO = ("chrome-extension://", "moz-extension://", "extension://", "safari-web-extension://")
LIMITE_CORPO = 256 * 1024


def origem_permitida(origem: str | None) -> bool:
    return not origem or origem.startswith(ORIGENS_EXTENSAO)


class Servidor(QObject):
    pedido = Signal(dict)       # download vindo do navegador
    abrir = Signal(list)        # outra cópia do programa pediu para mostrar a janela (com links, se houver)

    def __init__(self, porta: int = PORTA):
        super().__init__()
        self.porta = porta
        self.ultimo_contato_extensao = 0.0
        self.navegador = ""
        self.capturar = True
        self.versao_extensao = ""   # versão da extensão que falou com o programa (vazia nas antigas)
        self.contatos: dict[str, tuple[float, str]] = {}    # navegador -> (último contato, versão da extensão)        # a extensão consulta isto antes de capturar cada download
        self._srv: ThreadingHTTPServer | None = None

    @property
    def extensao_conectada(self) -> bool:
        return time.time() - self.ultimo_contato_extensao < 120

    def iniciar(self) -> bool:
        dono = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _responder(self, codigo: int, dados: dict | None = None):
                corpo = json.dumps(dados or {}, ensure_ascii=False).encode("utf-8")
                self.send_response(codigo)
                origem = self.headers.get("Origin")
                if origem and origem_permitida(origem):
                    self.send_header("Access-Control-Allow-Origin", origem)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(corpo)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(corpo)

            def _autorizado(self) -> bool:
                return self.headers.get("X-Convergio") == "1" and origem_permitida(self.headers.get("Origin"))

            def _contato(self):
                origem = self.headers.get("Origin") or ""
                if origem.startswith(ORIGENS_EXTENSAO):
                    dono.ultimo_contato_extensao = time.time()
                    dono.navegador = self.headers.get("X-Convergio-Navegador", "") or dono.navegador
                    dono.versao_extensao = self.headers.get("X-Convergio-Extensao", "") or "antiga"
                    if dono.navegador:
                        dono.contatos[dono.navegador] = (time.time(), dono.versao_extensao)

            def do_OPTIONS(self):
                self._responder(403, {"erro": "não permitido"})

            def do_GET(self):
                if not self._autorizado():
                    return self._responder(403, {"erro": "não permitido"})
                if self.path.split("?")[0] == "/ping":
                    self._contato()
                    return self._responder(200, {"app": APP_NAME, "versao": __version__, "capturar": dono.capturar})
                self._responder(404, {"erro": "não encontrado"})

            def do_POST(self):
                if not self._autorizado():
                    return self._responder(403, {"erro": "não permitido"})
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    if n > LIMITE_CORPO:
                        return self._responder(413, {"erro": "pedido grande demais"})
                    dados = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                except (ValueError, UnicodeDecodeError):
                    return self._responder(400, {"erro": "JSON inválido"})
                caminho = self.path.split("?")[0]
                if caminho == "/baixar":
                    url = str(dados.get("url", ""))
                    if not url.lower().startswith(("http://", "https://")):
                        return self._responder(400, {"erro": "link inválido"})
                    self._contato()
                    dono.pedido.emit(dados)
                    return self._responder(200, {"ok": True})
                if caminho == "/abrir":
                    dono.abrir.emit([str(u) for u in dados.get("links", [])])
                    return self._responder(200, {"ok": True})
                self._responder(404, {"erro": "não encontrado"})

        try:
            self._srv = ThreadingHTTPServer(("127.0.0.1", self.porta), H)
        except OSError:
            return False
        self._srv.daemon_threads = True
        threading.Thread(target=self._srv.serve_forever, daemon=True).start()
        return True

    def parar(self):
        if self._srv:
            self._srv.shutdown()
            self._srv.server_close()
            self._srv = None


def _pedido(caminho: str, dados: dict | None = None, porta: int = PORTA, timeout: float = 2.0):
    corpo = None if dados is None else json.dumps(dados).encode("utf-8")
    req = urllib.request.Request(f"http://127.0.0.1:{porta}{caminho}", data=corpo, method="POST" if corpo else "GET",
                                 headers={"X-Convergio": "1", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def instancia_aberta(porta: int = PORTA) -> bool:
    try:
        return _pedido("/ping", porta=porta, timeout=1.0).get("app") == APP_NAME
    except Exception:  # noqa: BLE001
        return False


def entregar_a_instancia_aberta(links: list[str], porta: int = PORTA) -> bool:
    """Se o Convergio já estiver aberto, entrega os links a ele e devolve True (esta cópia deve encerrar)."""
    try:
        if _pedido("/ping", porta=porta, timeout=1.0).get("app") != APP_NAME:
            return False
        _pedido("/abrir", {"links": links}, porta=porta)
        return True
    except Exception:  # noqa: BLE001
        return False
