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

    class Servidor(ThreadingHTTPServer):
        def handle_error(self, request, client_address):
            pass  # conexões interrompidas de propósito (pausa/quedas) não são erro do teste

    srv = Servidor(("127.0.0.1", 0), H)
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
        # nome gigante (código no lugar do nome, como alguns sites fazem): tem que ser encurtado e funcionar
        d = Download(base + "/arquivo.bin", pasta, 8, nome="VTN4q5w38fB7mI2HpCxs0KVFKN-" * 12)
        d.iniciar()
        d.aguardar(120)
        ok = d.status == CONCLUIDO and len(d.nome) <= 150
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} nome longo demais encurtado ({len(d.nome)} caracteres) {d.erro}")
        if t16 * 3 > t1:
            falhas += 1
            log(f"ERRO aceleração insuficiente: 1 conexão {t1:.1f}s × 16 conexões {t16:.1f}s")
    finally:
        srv.shutdown()
        shutil.rmtree(pasta, ignore_errors=True)
    return falhas


def testar_integracao(log, app):
    """Servidor local: aceita a extensão, recusa páginas da web, repassa cookies e referer."""
    import json
    import urllib.error
    import urllib.request
    from .integracao import Servidor
    falhas = 0
    srv = Servidor(porta=47999)
    recebidos = []
    srv.pedido.connect(recebidos.append)
    if not srv.iniciar():
        log("ERRO servidor de integração não iniciou")
        return 1

    def post(dados, cab):
        req = urllib.request.Request("http://127.0.0.1:47999/baixar", data=json.dumps(dados).encode(),
                                     headers={"Content-Type": "application/json", **cab}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code

    casos = [
        ("extensão do navegador aceita", {"X-Convergio": "1", "Origin": "chrome-extension://abc"}, 200),
        ("página da web bloqueada", {"X-Convergio": "1", "Origin": "https://site-malicioso.com"}, 403),
        ("pedido sem cabeçalho bloqueado", {"Origin": "chrome-extension://abc"}, 403),
    ]
    for nome, cab, esperado in casos:
        cod = post({"url": "https://exemplo.com/a.zip", "cookies": "sessao=1", "referrer": "https://exemplo.com/"}, cab)
        ok = cod == esperado
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} {nome} (HTTP {cod})")
    for _ in range(20):
        app.processEvents()
        time.sleep(0.02)
    ok = len(recebidos) == 1 and recebidos[0].get("cookies") == "sessao=1" and srv.extensao_conectada
    falhas += not ok
    log(f"{'OK ' if ok else 'ERRO'} pedido entregue ao programa com cookies ({len(recebidos)} recebido)")
    srv.parar()
    return falhas


def executar(argv):
    i = argv.index("--selftest")
    saida = argv[i + 1] if len(argv) > i + 1 else None
    linhas = []

    def log(m):
        linhas.append(m)
        if sys.stdout:                      # o executável não tem console
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
        falhas += testar_integracao(log, app)
        j = Janela()
        j.atualizador.verificar_auto = lambda: None
        j.show()
        app.processEvents()
        ok = not j.windowIcon().isNull() and j.tab.columnCount() == 7 and j.tray.contextMenu() is not None
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} janela, ícone e bandeja")
        # download vindo do navegador sem perguntar: entra na lista com os cookies
        j.settings.setValue("perguntar_navegador", "false")
        j.ed_pasta.setText(tempfile.mkdtemp(prefix="convergio-nav-"))
        j.receber_pedido({"url": "http://127.0.0.1:9/arquivo.zip", "cookies": "sessao=1",
                          "referrer": "https://exemplo.com/", "nome": "arquivo.zip"})
        d = j.downloads[-1] if j.downloads else None
        ok = bool(d) and d.headers.get("Cookie") == "sessao=1" and d.nome == "arquivo.zip"
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} download do navegador entra na fila com os cookies")
        # recursos da 1.2: pastas por tipo, limite, vários links, configurações, navegadores
        from .motor import LIMITADOR, categoria_do_arquivo
        from .recursos import DialogoConfiguracoes, DialogoVariosLinks, navegadores_instalados
        ok = categoria_do_arquivo("filme.MKV") == "Vídeos" and categoria_do_arquivo("x.zip") == "Compactados" \
            and categoria_do_arquivo("x.xyz") == ""
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} pastas por tipo")
        j.settings.setValue("limite_kb", 500)
        j.aplicar_limite(True)
        ok = LIMITADOR.limite == 500 * 1024
        j.aplicar_limite(False)
        ok = ok and LIMITADOR.limite == 0
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} limite de velocidade liga e desliga")
        ok = DialogoVariosLinks(j, "a https://a.com/1.zip b https://b.com/2.rar").links() == \
            ["https://a.com/1.zip", "https://b.com/2.rar"]
        falhas += not ok
        log(f"{'OK ' if ok else 'ERRO'} vários links")
        navs = navegadores_instalados()
        cfg = DialogoConfiguracoes(j, DialogoConfiguracoes.ABA_NAVEGADORES)
        cfg.show()
        app.processEvents()
        cfg.close()
        log(f"OK  configurações abrem; navegadores encontrados: {', '.join(n['nome'] for n in navs) or 'nenhum'}")
        j.settings.remove("limite_kb")
        j.settings.remove("limite_ativo")
        j.settings.remove("perguntar_navegador")
        for x in j.downloads:
            x.pausar()
        j.timer.stop()
        j.hide()
    except Exception as e:  # noqa: BLE001
        import traceback
        falhas += 1
        log("ERRO " + "".join(traceback.format_exception(e)))
    codigo = 1 if falhas else 0
    log("RESULTADO: " + ("tudo certo" if not falhas else f"{falhas} falha(s)") + f" (código {codigo})")
    if saida:
        with open(saida, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
    for fluxo in (sys.stdout, sys.stderr):
        if fluxo:
            fluxo.flush()
    if sys.platform == "win32":
        # encerra na hora, sem descarregar as DLLs do Qt (threads de rede ainda podem estar abertas)
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.GetCurrentProcess.restype = wintypes.HANDLE
        k.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k.TerminateProcess(k.GetCurrentProcess(), codigo)
    os._exit(codigo)
