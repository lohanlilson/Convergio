"""Autoteste: sobe um servidor HTTP local (com e sem suporte a Range, limitando a velocidade por conexão),
baixa arquivos com o motor e confere a integridade. Também abre a janela principal.
Usado pelo GitHub Actions no executável gerado: Convergio.exe --selftest saida.txt"""
import hashlib
import os
import random
import re
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POR_CONEXAO = 4 * 1024 * 1024


def servidor(dados: bytes):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/redir"):
                self.send_response(302)
                self.send_header("Location", "/arquivo.bin")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            sem_range, falha = self.path.startswith("/norange"), self.path.startswith("/falha")
            ini, fim = 0, len(dados) - 1
            rg = self.headers.get("Range")
            if rg and not sem_range:
                m = re.match(r"bytes=(\d+)-(\d*)", rg)
                ini = int(m.group(1))
                fim = min(fim, int(m.group(2)) if m.group(2) else fim)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{len(dados)}")
            else:
                self.send_response(200)
            self.send_header("Content-Length", str(fim - ini + 1))
            self.send_header("Content-Disposition", 'attachment; filename="teste convergio.bin"')
            if falha:
                self.send_header("Connection", "close")
            self.end_headers()
            t0, env, pos = time.monotonic(), 0, ini
            while pos <= fim:
                bloco = dados[pos:min(pos + 65536, fim + 1)]
                if falha and random.random() < 0.02:
                    self.close_connection = True
                    return
                try:
                    self.wfile.write(bloco)
                except OSError:
                    return
                pos += len(bloco)
                env += len(bloco)
                espera = env / POR_CONEXAO - (time.monotonic() - t0)
                if espera > 0:
                    time.sleep(espera)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


def testar_motor(log, tamanho=24 * 1024 * 1024):
    from .motor import CONCLUIDO, Download
    dados = random.Random(7).randbytes(tamanho)
    ref = hashlib.md5(dados).hexdigest()
    srv, base = servidor(dados)
    pasta = tempfile.mkdtemp(prefix="convergio-teste-")
    falhas = 0

    def caso(nome, url, con, pausar_em=None):
        nonlocal falhas
        t = time.time()
        d = Download(base + url, pasta, con)
        d.iniciar()
        if pausar_em:
            time.sleep(pausar_em)
            d.pausar()
            d.aguardar()
            d = Download(base + url, pasta, con, nome=d.nome)   # simula reabrir o programa
            d.iniciar()
        d.aguardar(300)
        ok = d.status == CONCLUIDO and hashlib.md5(open(d.caminho, "rb").read()).hexdigest() == ref
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} {nome:22} {time.time() - t:5.1f}s  trechos={len(d.segmentos):2}  {d.erro}")
        return time.time() - t

    try:
        t1 = caso("1 conexão", "/arquivo.bin", 1)
        t16 = caso("16 conexões", "/arquivo.bin", 16)
        caso("redirecionamento", "/redir", 16)
        caso("pausar e retomar", "/arquivo.bin", 8, pausar_em=0.5)
        caso("quedas de conexão", "/falha", 16)
        caso("servidor sem Range", "/norange", 16)
        if t16 * 3 > t1:
            falhas += 1
            log(f"ERRO aceleração insuficiente: 1 conexão {t1:.1f}s × 16 conexões {t16:.1f}s")
    finally:
        srv.shutdown()
        shutil.rmtree(pasta, ignore_errors=True)
    return falhas


def executar(argv):
    i = argv.index("--selftest")
    saida = argv[i + 1] if len(argv) > i + 1 else None
    linhas = []

    def log(m):
        linhas.append(m)
        print(m, flush=True)

    from . import APP_NAME, __version__
    log(f"{APP_NAME} {__version__} — autoteste")
    falhas = 0
    try:
        falhas += testar_motor(log)
        from PySide6.QtWidgets import QApplication
        from . import tema
        from .janela import Janela
        app = QApplication.instance() or QApplication([])
        tema.aplicar(app, False)
        j = Janela()
        j.atualizador.verificar_auto = lambda: None
        j.show()
        app.processEvents()
        ok = not j.windowIcon().isNull() and j.tab.columnCount() == 7
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} janela e ícone")
        j.timer.stop()
        j.hide()
    except Exception as e:  # noqa: BLE001
        import traceback
        falhas += 1
        log("ERRO " + "".join(traceback.format_exception(e)))
    log("RESULTADO: " + ("tudo certo" if not falhas else f"{falhas} falha(s)"))
    if saida:
        with open(saida, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
    sys.stdout.flush()
    os._exit(1 if falhas else 0)
