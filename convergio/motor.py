"""
Motor de download segmentado (estilo IDM).

- Várias conexões HTTP em paralelo, cada uma baixando um trecho (Range).
- Segmentação dinâmica: quando uma conexão termina seu trecho, ela divide ao meio
  o maior trecho restante e assume a segunda metade (nenhuma conexão fica ociosa).
- Reutilização de conexão (keep-alive): cada trabalhador mantém sua própria sessão.
- Retomada: o estado é salvo em <arquivo>.part.json e continua de onde parou.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from urllib.parse import unquote, urlparse

import requests
import urllib3
from requests.adapters import HTTPAdapter

CHUNK = 256 * 1024            # bytes lidos por vez
MIN_SPLIT = 1024 * 1024       # só divide trechos com pelo menos 2x isso restante
MAX_TENTATIVAS = 10
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
DESCONHECIDO = 1 << 62

NA_FILA = "Na fila"
CONECTANDO = "Conectando"
BAIXANDO = "Baixando"
PAUSADO = "Pausado"
CONCLUIDO = "Concluído"
ERRO = "Erro"


def fmt_bytes(n: float | None) -> str:
    if n is None:
        return "?"
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.2f} {u}"
        n /= 1024
    return ""


def fmt_tempo(s: float | None) -> str:
    if s is None or s < 0 or s > 86400 * 30:
        return "—"
    s = int(s)
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else (f"{m}m {s:02d}s" if m else f"{s}s")


class Segmento:
    __slots__ = ("start", "end", "pos", "ativo")

    def __init__(self, start: int, end: int, pos: int | None = None):
        self.start = start
        self.end = end                      # inclusivo
        self.pos = start if pos is None else pos
        self.ativo = False

    @property
    def restante(self) -> int:
        return max(0, self.end - self.pos + 1)

    @property
    def concluido(self) -> bool:
        return self.pos > self.end


class Download:
    def __init__(self, url: str, pasta: str, conexoes: int = 16,
                 nome: str | None = None, headers: dict | None = None):
        self.url = url.strip()
        self.url_final = self.url
        self.pasta = pasta
        self.conexoes = max(1, min(32, conexoes))
        self.nome = nome
        self.headers = {"User-Agent": UA, "Accept-Encoding": "identity", **(headers or {})}
        self.caminho: str | None = None
        self.tamanho: int | None = None
        self.aceita_range = False
        self.segmentos: list[Segmento] = []
        self.baixado = 0
        self.velocidade = 0.0
        self.status = NA_FILA
        self.erro = ""
        self.lock = threading.Lock()
        self._parar = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ controle
    @property
    def rodando(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def iniciar(self):
        if self.rodando or self.status == CONCLUIDO:
            return
        self._parar.clear()
        self.erro = ""
        self.status = CONECTANDO
        self._thread = threading.Thread(target=self._executar, daemon=True)
        self._thread.start()

    def pausar(self):
        self._parar.set()
        if not self.rodando and self.status in (NA_FILA, ERRO):
            self.status = PAUSADO

    def aguardar(self, timeout: float | None = None):
        if self._thread:
            self._thread.join(timeout)

    # ------------------------------------------------------------ info p/ interface
    @property
    def progresso(self) -> float:
        if self.status == CONCLUIDO:
            return 1.0
        if not self.tamanho:
            return -1
        return min(1.0, self.baixado / self.tamanho)

    @property
    def tempo_restante(self) -> float | None:
        if not self.tamanho or self.velocidade <= 0:
            return None
        return (self.tamanho - self.baixado) / self.velocidade

    @property
    def conexoes_ativas(self) -> int:
        with self.lock:
            return sum(1 for s in self.segmentos if s.ativo and not s.concluido)

    def mapa(self) -> list[tuple[int, int, int, bool]]:
        with self.lock:
            return [(s.start, s.end, s.pos, s.ativo) for s in self.segmentos]

    # ------------------------------------------------------------ internos
    @property
    def _part(self) -> str:
        return self.caminho + ".part"

    @property
    def _meta(self) -> str:
        return self.caminho + ".part.json"

    def _sessao(self) -> requests.Session:
        s = requests.Session()
        s.headers.update(self.headers)
        ad = HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
        s.mount("http://", ad)
        s.mount("https://", ad)
        return s

    def _sondar(self):
        """Descobre tamanho, suporte a Range, nome do arquivo e URL final (após redirecionamentos)."""
        with self._sessao() as s:
            r = s.get(self.url, headers={"Range": "bytes=0-0"}, stream=True,
                      timeout=(15, 30), allow_redirects=True)
            try:
                r.raise_for_status()
                self.url_final = r.url
                self.aceita_range = False
                if r.status_code == 206:
                    m = re.search(r"/(\d+)\s*$", r.headers.get("Content-Range", ""))
                    if m:
                        self.tamanho = int(m.group(1))
                        self.aceita_range = True
                if not self.aceita_range:
                    cl = r.headers.get("Content-Length", "")
                    self.tamanho = int(cl) if cl.isdigit() else None
                if not self.nome:
                    self.nome = self._nome_arquivo(r)
            finally:
                r.close()

    @staticmethod
    def _nome_arquivo(r: requests.Response) -> str:
        cd = r.headers.get("Content-Disposition", "")
        nome = ""
        m = re.search(r"filename\*\s*=\s*[\w-]+'[^']*'([^;]+)", cd, re.I)
        if m:
            nome = unquote(m.group(1).strip().strip('"'))
        else:
            m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
            if m:
                try:
                    nome = m.group(1).encode("latin-1").decode("utf-8")
                except UnicodeError:
                    nome = m.group(1)
        if not nome:
            nome = unquote(os.path.basename(urlparse(r.url).path))
        nome = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "_", nome).strip(" .")
        return nome or "download"

    def _caminho_livre(self):
        base, ext = os.path.splitext(self.nome)
        i = 1
        while os.path.exists(self.caminho) or os.path.exists(self._part):
            self.nome = f"{base} ({i}){ext}"
            self.caminho = os.path.join(self.pasta, self.nome)
            i += 1

    def _carregar_estado(self) -> bool:
        if not (os.path.exists(self._meta) and os.path.exists(self._part)):
            return False
        try:
            with open(self._meta, encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return False
        if d.get("url") != self.url or d.get("tamanho") != self.tamanho:
            return False
        self.segmentos = [Segmento(a, b, p) for a, b, p in d["segmentos"]]
        self.baixado = sum(s.pos - s.start for s in self.segmentos)
        return True

    def _salvar_estado(self):
        if not (self.aceita_range and self.caminho and self.segmentos):
            return
        with self.lock:
            d = {"url": self.url, "tamanho": self.tamanho, "nome": self.nome,
                 "segmentos": [[s.start, s.end, s.pos] for s in self.segmentos if not s.concluido]}
        tmp = self._meta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, self._meta)

    def _preparar(self):
        self._caminho_livre()
        with open(self._part, "wb") as f:
            if self.tamanho:
                f.truncate(self.tamanho)          # pré-aloca o arquivo
        self.baixado = 0
        if self.aceita_range and self.tamanho:
            n = max(1, min(self.conexoes, self.tamanho // MIN_SPLIT))
            passo = self.tamanho // n
            self.segmentos = [Segmento(i * passo, (i + 1) * passo - 1 if i < n - 1 else self.tamanho - 1)
                              for i in range(n)]
        else:
            fim = self.tamanho - 1 if self.tamanho else DESCONHECIDO
            self.segmentos = [Segmento(0, fim)]

    def _proximo_segmento(self) -> Segmento | None:
        """Chamado com self.lock adquirido. Segmentação dinâmica."""
        livres = [s for s in self.segmentos if not s.ativo and not s.concluido]
        if livres:
            s = max(livres, key=lambda x: x.restante)
            s.ativo = True
            return s
        if not self.aceita_range:
            return None
        ativos = [s for s in self.segmentos if s.ativo and not s.concluido]
        if not ativos:
            return None
        v = max(ativos, key=lambda x: x.restante)
        if v.restante < 2 * MIN_SPLIT:
            return None
        meio = v.pos + v.restante // 2
        novo = Segmento(meio, v.end)
        v.end = meio - 1
        novo.ativo = True
        self.segmentos.append(novo)
        return novo

    def _trabalhador(self):
        sess = self._sessao()
        seg = None
        try:
            with self.lock:
                seg = self._proximo_segmento()
            while seg is not None and not self._parar.is_set():
                try:
                    ok = self._baixar_segmento(sess, seg)
                except Exception as e:  # noqa: BLE001
                    self.erro = str(e)
                    ok = False
                if not ok:
                    return
                with self.lock:
                    seg.ativo = False
                    seg = self._proximo_segmento()
        finally:
            sess.close()
            if seg is not None:
                with self.lock:
                    seg.ativo = False

    def _baixar_segmento(self, sess: requests.Session, seg: Segmento) -> bool:
        tentativas = 0
        with open(self._part, "r+b") as fh:
            while not seg.concluido and not self._parar.is_set():
                try:
                    hdr = {"Range": f"bytes={seg.pos}-{seg.end}"} if self.aceita_range else {}
                    with sess.get(self.url_final, headers=hdr, stream=True, timeout=(15, 30)) as r:
                        if r.status_code in (401, 403, 404, 410, 416):
                            raise requests.HTTPError(f"HTTP {r.status_code}")
                        r.raise_for_status()
                        if self.aceita_range and r.status_code != 206:
                            raise IOError("o servidor ignorou o pedido de trecho (Range)")
                        for chunk in r.raw.stream(CHUNK, decode_content=False):
                            if self._parar.is_set():
                                return False
                            with self.lock:
                                n = min(len(chunk), seg.end - seg.pos + 1)
                                at = seg.pos
                                seg.pos += n
                                self.baixado += n
                            if n > 0:
                                fh.seek(at)
                                fh.write(chunk if n == len(chunk) else chunk[:n])
                                tentativas = 0
                            if seg.concluido:
                                break
                    if not seg.concluido:
                        if seg.end == DESCONHECIDO:          # tamanho desconhecido: fim do fluxo = fim do arquivo
                            with self.lock:
                                seg.end = seg.pos - 1
                                self.tamanho = seg.pos
                            break
                        raise IOError("conexão encerrada antes do fim do trecho")
                except (requests.RequestException, urllib3.exceptions.HTTPError, IOError) as e:
                    if isinstance(e, OSError) and e.errno is not None and not isinstance(e, TimeoutError):
                        self.erro = f"Erro de disco: {e}"          # disco cheio, permissão etc.
                        return False
                    if not self.aceita_range:                       # sem Range: recomeça do zero
                        with self.lock:
                            self.baixado -= seg.pos - seg.start
                            seg.pos = seg.start
                    tentativas += 1
                    if tentativas > MAX_TENTATIVAS:
                        self.erro = str(e)
                        return False
                    if tentativas >= 3:
                        self.url_final = self.url                   # link assinado pode ter expirado
                    self._parar.wait(min(30, 2 ** tentativas))
        return seg.concluido

    def _executar(self):
        try:
            if not self.segmentos or not self.aceita_range:
                antigo = self.caminho
                self._sondar()
                os.makedirs(self.pasta, exist_ok=True)
                self.caminho = antigo or os.path.join(self.pasta, self.nome)
                if not (self.aceita_range and self._carregar_estado()):
                    if antigo and os.path.exists(self._part):
                        os.remove(self._part)          # sem Range não dá para retomar
                    self._preparar()
            if self._parar.is_set():
                self._salvar_estado()
                self.status = PAUSADO
                return

            self.status = BAIXANDO
            n = self.conexoes if self.aceita_range else 1
            threads = [threading.Thread(target=self._trabalhador, daemon=True) for _ in range(n)]
            for t in threads:
                t.start()

            t0, b0, ult_salvo = time.monotonic(), self.baixado, time.monotonic()
            while any(t.is_alive() for t in threads):
                time.sleep(0.5)
                agora = time.monotonic()
                inst = (self.baixado - b0) / max(1e-6, agora - t0)
                self.velocidade = inst if self.velocidade == 0 else 0.7 * self.velocidade + 0.3 * inst
                t0, b0 = agora, self.baixado
                if agora - ult_salvo > 2:
                    self._salvar_estado()
                    ult_salvo = agora
                # reaproveita conexões que caíram por erro, se ainda há trabalho
                if not self._parar.is_set() and self.aceita_range:
                    vivos = [t for t in threads if t.is_alive()]
                    if 0 < len(vivos) < n and any(not s.ativo and not s.concluido for s in self.segmentos):
                        t = threading.Thread(target=self._trabalhador, daemon=True)
                        t.start()
                        threads = vivos + [t]
            self.velocidade = 0.0

            if all(s.concluido for s in self.segmentos):
                if self.tamanho is not None and self.baixado < self.tamanho:
                    raise IOError("arquivo incompleto")
                os.replace(self._part, self.caminho)
                if os.path.exists(self._meta):
                    os.remove(self._meta)
                self.status = CONCLUIDO
            elif self._parar.is_set():
                self._salvar_estado()
                self.status = PAUSADO
            else:
                self._salvar_estado()
                self.erro = self.erro or "falha nas conexões"
                self.status = ERRO
        except Exception as e:  # noqa: BLE001
            self.velocidade = 0.0
            self.erro = str(e)
            try:
                self._salvar_estado()
            except Exception:  # noqa: BLE001
                pass
            self.status = PAUSADO if self._parar.is_set() else ERRO
