"""Download de vídeos em streaming (HLS / .m3u8).

O vídeo é uma lista de centenas de pedaços pequenos. O Convergio baixa os pedaços com várias conexões,
e no fim junta tudo num único .mp4 com o FFmpeg (sem recodificar, então é rápido e não perde qualidade).
O FFmpeg não vem no instalador: é baixado uma vez, do PyPI (pacote imageio-ffmpeg), quando o primeiro
vídeo precisa dele.

Não funciona com vídeos protegidos por DRM nem com transmissões ao vivo.
"""
from __future__ import annotations

import hashlib
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

import requests

from .motor import (BAIXANDO, CONCLUIDO, CONECTANDO, ERRO, LIMITADOR, PAUSADO, Download, categoria_do_arquivo,
                    nome_seguro)

RE_ATRIB = re.compile(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)')
PYPI_FFMPEG = "https://pypi.org/pypi/imageio-ffmpeg/json"
PASTA_FFMPEG = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / "Convergio" / "ffmpeg"
SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW


def _atributos(linha: str) -> dict:
    return {k: v.strip('"') for k, v in RE_ATRIB.findall(linha.split(":", 1)[1] if ":" in linha else "")}


# ------------------------------------------------------------------ FFmpeg sob demanda
def caminho_ffmpeg() -> str | None:
    """FFmpeg já disponível neste computador (sem baixar)."""
    env = os.environ.get("CONVERGIO_FFMPEG")
    if env and os.path.exists(env):
        return env
    local = PASTA_FFMPEG / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if local.exists():
        return str(local)
    return shutil.which("ffmpeg")


def baixar_ffmpeg(parar: threading.Event | None = None) -> str:
    """Baixa o FFmpeg (uma vez só) do pacote imageio-ffmpeg no PyPI, conferindo o SHA-256."""
    padrao = {"win32": r"-win_amd64\.whl$", "linux": r"-manylinux.*x86_64\.whl$"}.get(sys.platform)
    if not padrao:
        raise IOError("FFmpeg não encontrado neste computador")
    info = requests.get(PYPI_FFMPEG, timeout=30).json()
    arq = next((u for u in info["urls"] if re.search(padrao, u["filename"])), None)
    if not arq:
        raise IOError("pacote do FFmpeg não encontrado")
    tmp = tempfile.mkdtemp(prefix="convergio-ffmpeg-")
    try:
        d = Download(arq["url"], tmp, 8, nome="ffmpeg.whl")
        d.iniciar()
        while d.rodando:
            if parar is not None and parar.is_set():
                d.pausar()
                d.aguardar(10)
                raise IOError("cancelado")
            time.sleep(0.2)
        if d.status != CONCLUIDO:
            raise IOError(f"não foi possível baixar o FFmpeg: {d.erro}")
        h = hashlib.sha256()
        with open(d.caminho, "rb") as f:
            for bloco in iter(lambda: f.read(1 << 20), b""):
                h.update(bloco)
        if h.hexdigest() != arq["digests"]["sha256"]:
            raise IOError("o FFmpeg baixado está corrompido")
        with zipfile.ZipFile(d.caminho) as z:
            membro = next(n for n in z.namelist() if "/binaries/ffmpeg" in n and not n.endswith("/"))
            PASTA_FFMPEG.mkdir(parents=True, exist_ok=True)
            destino = PASTA_FFMPEG / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
            with z.open(membro) as origem, open(str(destino) + ".tmp", "wb") as saida:
                shutil.copyfileobj(origem, saida)
            os.replace(str(destino) + ".tmp", destino)
            if sys.platform != "win32":
                os.chmod(destino, 0o755)
        return str(destino)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ------------------------------------------------------------------ playlist
class Faixa:
    """Uma lista de pedaços (vídeo ou áudio) já interpretada."""

    def __init__(self, prefixo: str):
        self.prefixo = prefixo
        self.sequencia = 0
        self.duracao_alvo = 10
        self.itens: list[dict] = []        # {"arquivo", "url", "faixa_bytes", "dur", "chave", "mapa", "descont"}
        self.extras: dict[str, tuple] = {}  # arquivo local -> (url, faixa_bytes) de chaves e cabeçalhos (EXT-X-MAP)

    def interpretar(self, texto: str, base: str):
        chave, mapa, descont, faixa_bytes, dur = None, None, False, None, 0.0
        fim_anterior = 0
        terminou = False
        for linha in (x.strip() for x in texto.splitlines()):
            if not linha:
                continue
            if linha.startswith("#EXT-X-MEDIA-SEQUENCE"):
                self.sequencia = int(linha.split(":")[1])
            elif linha.startswith("#EXT-X-TARGETDURATION"):
                self.duracao_alvo = int(float(linha.split(":")[1]))
            elif linha.startswith("#EXT-X-KEY"):
                a = _atributos(linha)
                metodo = a.get("METHOD", "NONE")
                if metodo == "NONE":
                    chave = None
                elif metodo == "AES-128":
                    nome = f"{self.prefixo}chave{len([e for e in self.extras if 'chave' in e])}.key"
                    conhecida = next((n for n, (u, _) in self.extras.items() if u == urljoin(base, a["URI"])), None)
                    nome = conhecida or nome
                    self.extras[nome] = (urljoin(base, a["URI"]), None)
                    chave = (nome, a.get("IV"))
                else:
                    raise IOError("este vídeo é protegido contra cópia (DRM) e não pode ser baixado")
            elif linha.startswith("#EXT-X-MAP"):
                a = _atributos(linha)
                nome = f"{self.prefixo}cabecalho{len([e for e in self.extras if 'cabecalho' in e])}.mp4"
                fb = None
                if a.get("BYTERANGE"):
                    tam, _, ini = a["BYTERANGE"].partition("@")
                    fb = (int(ini or 0), int(ini or 0) + int(tam) - 1)
                self.extras[nome] = (urljoin(base, a["URI"]), fb)
                mapa = nome
            elif linha.startswith("#EXT-X-DISCONTINUITY") and not linha.startswith("#EXT-X-DISCONTINUITY-SEQUENCE"):
                descont = True
            elif linha.startswith("#EXT-X-BYTERANGE"):
                tam, _, ini = linha.split(":")[1].partition("@")
                ini = int(ini) if ini else fim_anterior
                faixa_bytes = (ini, ini + int(tam) - 1)
                fim_anterior = ini + int(tam)
            elif linha.startswith("#EXTINF"):
                dur = float(linha.split(":")[1].split(",")[0] or 0)
            elif linha.startswith("#EXT-X-ENDLIST"):
                terminou = True
            elif not linha.startswith("#"):
                ext = ".mp4" if mapa else ".ts"
                self.itens.append({"arquivo": f"{self.prefixo}{len(self.itens):06d}{ext}", "url": urljoin(base, linha),
                                   "faixa_bytes": faixa_bytes, "dur": dur, "chave": chave, "mapa": mapa,
                                   "descont": descont})
                descont, faixa_bytes = False, None
        if not self.itens:
            raise IOError("a lista do vídeo está vazia")
        if not terminou:
            raise IOError("transmissões ao vivo não são suportadas")

    def playlist_local(self) -> str:
        linhas = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{self.duracao_alvo}",
                  f"#EXT-X-MEDIA-SEQUENCE:{self.sequencia}", "#EXT-X-PLAYLIST-TYPE:VOD"]
        chave, mapa = None, None
        for it in self.itens:
            if it["descont"]:
                linhas.append("#EXT-X-DISCONTINUITY")
            if it["chave"] != chave:
                chave = it["chave"]
                if chave:
                    linhas.append(f'#EXT-X-KEY:METHOD=AES-128,URI="{chave[0]}"' + (f",IV={chave[1]}" if chave[1] else ""))
                else:
                    linhas.append("#EXT-X-KEY:METHOD=NONE")
            if it["mapa"] != mapa:
                mapa = it["mapa"]
                linhas.append(f'#EXT-X-MAP:URI="{mapa}"')
            linhas.append(f"#EXTINF:{it['dur']:.6f},")
            linhas.append(it["arquivo"])
        linhas.append("#EXT-X-ENDLIST")
        return "\n".join(linhas) + "\n"


def escolher_variante(texto: str, base: str) -> tuple[str, str | None]:
    """Da lista principal, devolve (lista do vídeo de maior qualidade, lista do áudio separado ou None)."""
    linhas = [x.strip() for x in texto.splitlines() if x.strip()]
    melhor, audio_grupo = None, None
    for i, linha in enumerate(linhas):
        if linha.startswith("#EXT-X-STREAM-INF"):
            a = _atributos(linha)
            url = next((x for x in linhas[i + 1:] if not x.startswith("#")), None)
            banda = int(a.get("BANDWIDTH", 0) or 0)
            if url and (melhor is None or banda > melhor[0]):
                melhor = (banda, urljoin(base, url))
                audio_grupo = a.get("AUDIO")
    if melhor is None:
        raise IOError("nenhuma qualidade de vídeo encontrada na lista")
    audio = None
    if audio_grupo:
        candidatos = []
        for linha in linhas:
            if linha.startswith("#EXT-X-MEDIA"):
                a = _atributos(linha)
                if a.get("TYPE") == "AUDIO" and a.get("GROUP-ID") == audio_grupo and a.get("URI"):
                    candidatos.append((a.get("DEFAULT") == "YES", urljoin(base, a["URI"])))
        if candidatos:
            audio = sorted(candidatos, reverse=True)[0][1]
    return melhor[1], audio


# ------------------------------------------------------------------ download
class DownloadHLS(Download):
    tipo = "hls"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.faixas: list[Faixa] = []
        self.total = 0
        self.feitos: set[str] = set()
        self._ativos = 0
        self.etapa = ""

    # ---- informações para a interface
    @property
    def progresso(self) -> float:
        if self.status == CONCLUIDO:
            return 1.0
        return len(self.feitos) / self.total if self.total else -1

    @property
    def tempo_restante(self):
        if not self.total or not self.feitos or self.velocidade <= 0:
            return None
        estimado = self.baixado / len(self.feitos) * self.total
        return max(0.0, (estimado - self.baixado) / self.velocidade)

    @property
    def conexoes_ativas(self) -> int:
        return self._ativos

    @property
    def total_mapa(self):
        return self.total or None

    def mapa(self):
        saida, i = [], 0
        for f in self.faixas:
            for it in f.itens:
                saida.append((i, i, i + 1 if it["arquivo"] in self.feitos else i, False))
                i += 1
        return saida

    # ---- execução
    def _texto(self, sess, url):
        r = sess.get(url, timeout=(15, 30))
        if r.status_code in (401, 403, 404, 410):
            raise IOError("o link expirou ou foi recusado pelo servidor — abra o vídeo de novo no navegador e use "
                          "Atualizar link")
        r.raise_for_status()
        r.encoding = "utf-8"
        return r.text, r.url

    def _preparar_lista(self):
        with self._sessao() as sess:
            texto, base = self._texto(sess, self.url)
            if "#EXT-X-STREAM-INF" in texto:
                video, audio = escolher_variante(texto, base)
            else:
                video, audio = base, None
            self.faixas = []
            for prefixo, url in (("v", video), ("a", audio)):
                if not url:
                    continue
                t, b = (texto, base) if url == base and prefixo == "v" else self._texto(sess, url)
                f = Faixa(prefixo)
                f.interpretar(t, b)
                self.faixas.append(f)
        self.total = sum(len(f.itens) + len(f.extras) for f in self.faixas)
        self.segmentos = [None] * self.total

    def _trabalhos(self):
        for f in self.faixas:
            for nome, (url, fb) in f.extras.items():
                yield nome, url, fb
            for it in f.itens:
                yield it["arquivo"], it["url"], it["faixa_bytes"]

    def _baixar_pedacos(self, pasta: str):
        fila: queue.Queue = queue.Queue()
        self.feitos = set()
        self.baixado = 0
        for nome, url, fb in self._trabalhos():
            destino = os.path.join(pasta, nome)
            if os.path.exists(destino) and os.path.getsize(destino) > 0:
                self.feitos.add(nome)
                self.baixado += os.path.getsize(destino)
            else:
                fila.put((nome, url, fb))
        falha: list[str] = []

        def trabalhador():
            sess = self._sessao()
            try:
                while not self._parar.is_set() and not falha:
                    try:
                        nome, url, fb = fila.get_nowait()
                    except queue.Empty:
                        return
                    self._ativos += 1
                    try:
                        self._baixar_um(sess, url, fb, os.path.join(pasta, nome))
                        self.feitos.add(nome)
                    except Exception as e:  # noqa: BLE001
                        if not self._parar.is_set():
                            falha.append(str(e))
                    finally:
                        self._ativos -= 1
            finally:
                sess.close()

        threads = [threading.Thread(target=trabalhador, daemon=True) for _ in range(min(self.conexoes, 16))]
        for t in threads:
            t.start()
        t0, b0 = time.monotonic(), self.baixado
        while any(t.is_alive() for t in threads):
            time.sleep(0.5)
            agora = time.monotonic()
            inst = (self.baixado - b0) / max(1e-6, agora - t0)
            self.velocidade = inst if self.velocidade == 0 else 0.7 * self.velocidade + 0.3 * inst
            t0, b0 = agora, self.baixado
            if self.feitos:
                self.tamanho = int(self.baixado / len(self.feitos) * self.total)
        self.velocidade = 0.0
        if falha:
            raise IOError(falha[0])

    def _baixar_um(self, sess, url, fb, destino):
        ultimo = None
        for tentativa in range(6):
            if self._parar.is_set():
                raise IOError("pausado")
            recebido = 0
            try:
                hdr = {"Range": f"bytes={fb[0]}-{fb[1]}"} if fb else {}
                with sess.get(url, headers=hdr, stream=True, timeout=(15, 30)) as r:
                    if r.status_code in (401, 403, 404, 410):
                        raise PermissionError("o link expirou ou foi recusado pelo servidor — abra o vídeo de novo no "
                                              "navegador e use Atualizar link")
                    r.raise_for_status()
                    with open(destino + ".tmp", "wb") as f:
                        for bloco in r.iter_content(64 * 1024):
                            if self._parar.is_set():
                                raise IOError("pausado")
                            LIMITADOR.consumir(len(bloco), self._parar)
                            f.write(bloco)
                            recebido += len(bloco)
                            with self.lock:
                                self.baixado += len(bloco)
                os.replace(destino + ".tmp", destino)
                return
            except PermissionError:
                raise
            except (requests.RequestException, OSError) as e:
                with self.lock:
                    self.baixado -= recebido
                ultimo = e
                self._parar.wait(min(10, 1.5 ** tentativa))
        raise IOError(f"falha ao baixar um trecho do vídeo: {ultimo}")

    def _juntar(self, pasta: str):
        self.etapa = "Preparando o conversor (só na primeira vez)"
        ffmpeg = caminho_ffmpeg() or baixar_ffmpeg(self._parar)
        self.etapa = "Juntando o vídeo"
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
        for f in self.faixas:
            with open(os.path.join(pasta, f"{f.prefixo}.m3u8"), "w", encoding="utf-8") as arq:
                arq.write(f.playlist_local())
            cmd += ["-allowed_extensions", "ALL", "-protocol_whitelist", "file,crypto,data", "-i", f"{f.prefixo}.m3u8"]
        saida = os.path.join(pasta, "saida.mp4")
        cmd += ["-c", "copy", "-movflags", "+faststart", saida]
        r = subprocess.run(cmd, cwd=pasta, capture_output=True, text=True, errors="replace", creationflags=SEM_JANELA)
        if r.returncode != 0 or not os.path.exists(saida):
            raise IOError("não foi possível juntar o vídeo: " + (r.stderr.strip().splitlines() or ["erro do FFmpeg"])[-1])
        os.replace(saida, self.caminho)

    def _executar(self):
        try:
            if not self.faixas:
                self._preparar_lista()
            if not self.caminho:
                base = os.path.splitext(self.nome or "video")[0]
                self.nome = nome_seguro(base + ".mp4")
                if self.por_tipo:
                    self.pasta = os.path.join(self.pasta, categoria_do_arquivo(self.nome))
                    self.por_tipo = False
                os.makedirs(self.pasta, exist_ok=True)
                self.caminho = os.path.join(self.pasta, self.nome)
                raiz, i = os.path.splitext(self.nome)[0], 1
                while os.path.exists(self.caminho) or os.path.exists(self.caminho + ".partes"):
                    self.nome = f"{raiz} ({i}).mp4"
                    self.caminho = os.path.join(self.pasta, self.nome)
                    i += 1
            pasta = self.caminho + ".partes"
            os.makedirs(pasta, exist_ok=True)
            if self._parar.is_set():
                self.status = PAUSADO
                return
            self.status = BAIXANDO
            self.etapa = ""
            self._baixar_pedacos(pasta)
            if self._parar.is_set():
                self.status = PAUSADO
                return
            self._juntar(pasta)
            shutil.rmtree(pasta, ignore_errors=True)
            self.tamanho = os.path.getsize(self.caminho)
            self.etapa = ""
            self.concluido_em = time.time()
            self.status = CONCLUIDO
        except Exception as e:  # noqa: BLE001
            self.velocidade = 0.0
            self.etapa = ""
            self.erro = str(e)
            self.status = PAUSADO if self._parar.is_set() else ERRO

    def trocar_link(self, url, headers=None):
        """Link novo: refaz a lista (os endereços dos pedaços mudam), mas mantém os pedaços já baixados."""
        super().trocar_link(url, headers)
        self.faixas = []
        self.feitos = set()


def criar_download(tipo: str | None, *a, **k) -> Download:
    return DownloadHLS(*a, **k) if tipo == "hls" else Download(*a, **k)


__all__ = ["DownloadHLS", "criar_download", "caminho_ffmpeg", "baixar_ffmpeg", "CONECTANDO"]
