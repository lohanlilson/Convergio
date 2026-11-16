"""Downloads por torrent e links magnet (libtorrent).

Aceita link magnet:, arquivo .torrent no computador ou link http(s) de um .torrent.
Quando termina, para de compartilhar (o Convergio é um baixador, não um cliente de compartilhamento).
O que já foi baixado é retomado depois de pausar ou fechar o programa (dados de retomada guardados).
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .motor import BAIXANDO, CONCLUIDO, CONECTANDO, ERRO, LIMITADOR, PAUSADO, UA, Download, nome_seguro

PASTA_DADOS = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home()) / "Convergio" / "torrents"
RE_MAGNET = re.compile(r"^magnet:\?\S*xt=urn:bt[im]h:", re.I)

_lt = None
_sessao = None
_lock = threading.RLock()
_resumos: dict[str, bytes] = {}           # info-hash → dados de retomada recebidos da libtorrent


def eh_torrent(url: str) -> bool:
    u = (url or "").strip()
    if RE_MAGNET.match(u):
        return True
    caminho = urlparse(u).path if u.lower().startswith(("http://", "https://")) else u
    return caminho.lower().endswith(".torrent")


def disponivel() -> bool:
    try:
        _biblioteca()
        return True
    except Exception:  # noqa: BLE001
        return False


def _biblioteca():
    global _lt
    if _lt is None:
        import libtorrent as lt
        _lt = lt
    return _lt


def sessao():
    """Sessão única da libtorrent, compartilhada por todos os torrents."""
    global _sessao
    with _lock:
        if _sessao is None:
            lt = _biblioteca()
            _sessao = lt.session({
                "user_agent": "Convergio",
                "listen_interfaces": "0.0.0.0:6881,[::]:6881",
                "alert_mask": lt.alert.category_t.status_notification | lt.alert.category_t.storage_notification
                | lt.alert.category_t.error_notification,
                "enable_dht": True, "enable_lsd": True, "enable_upnp": True, "enable_natpmp": True,
            })
        return _sessao


def _coletar_alertas():
    lt = _biblioteca()
    for a in sessao().pop_alerts():
        if isinstance(a, lt.save_resume_data_alert):
            try:
                _resumos[str(a.handle.info_hash())] = lt.write_resume_data_buf(a.params)
            except Exception:  # noqa: BLE001
                pass


def aplicar_limite():
    """Leva o limite de velocidade do Convergio (o fixo e o da velocidade inteligente) para a libtorrent."""
    if _sessao is not None:
        lim = LIMITADOR.efetivo
        _sessao.apply_settings({"download_rate_limit": lim, "upload_rate_limit": max(lim // 4, 0)})


class DownloadTorrent(Download):
    tipo = "torrent"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.conexoes = 0
        self._h = None
        self._pecas: list[bool] = []
        self._pares = 0
        self.pares_extras: list[tuple[str, int]] = []      # usado pelos testes (semeador local)
        if not self.nome:
            self.nome = self._nome_do_link()

    # ---- nomes e arquivos
    def _nome_do_link(self) -> str | None:
        u = self.url
        if u.lower().startswith("magnet:"):
            dn = parse_qs(urlparse(u).query).get("dn")
            return nome_seguro(unquote(dn[0])) if dn else None
        return None

    @property
    def chave(self) -> str:
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()

    @property
    def _arq_resumo(self) -> Path:
        return PASTA_DADOS / (self.chave + ".resume")

    @property
    def _arq_torrent(self) -> Path:
        return PASTA_DADOS / (self.chave + ".torrent")

    # ---- informações para a interface
    @property
    def progresso(self) -> float:
        if self.status == CONCLUIDO:
            return 1.0
        return min(1.0, self.baixado / self.tamanho) if self.tamanho else -1

    @property
    def conexoes_ativas(self) -> int:
        return self._pares

    @property
    def total_mapa(self):
        return len(self._pecas) or None

    def mapa(self):
        saida, i, p = [], 0, self._pecas
        while i < len(p):
            j = i
            while j < len(p) and p[j] == p[i]:
                j += 1
            saida.append((i, j, j if p[i] else i, False))
            i = j
        return saida

    # ---- execução
    def _parametros(self):
        lt = _biblioteca()
        PASTA_DADOS.mkdir(parents=True, exist_ok=True)
        if self._arq_resumo.exists():
            try:
                params = lt.read_resume_data(self._arq_resumo.read_bytes())
                params.save_path = self.pasta
                return params
            except Exception:  # noqa: BLE001
                pass
        u = self.url
        if u.lower().startswith("magnet:"):
            params = lt.parse_magnet_uri(u)
        else:
            if u.lower().startswith(("http://", "https://")):
                if not self._arq_torrent.exists():
                    import requests
                    r = requests.get(u, headers={"User-Agent": UA, **self.headers_extra}, timeout=30)
                    r.raise_for_status()
                    if not r.content.startswith(b"d"):
                        raise IOError("o link não é de um arquivo .torrent")
                    self._arq_torrent.write_bytes(r.content)
                dados = self._arq_torrent.read_bytes()
            else:
                if not os.path.exists(u):
                    raise IOError("arquivo .torrent não encontrado")
                dados = Path(u).read_bytes()
            params = lt.add_torrent_params()
            params.ti = lt.torrent_info(lt.bdecode(dados))
        params.save_path = self.pasta
        return params

    def _salvar_resumo(self, h, espera=5.0):
        lt = _biblioteca()
        try:
            chave = str(h.info_hash())
            _resumos.pop(chave, None)
            h.save_resume_data(lt.torrent_handle.save_info_dict)
            fim = time.monotonic() + espera
            while time.monotonic() < fim and chave not in _resumos:
                with _lock:
                    _coletar_alertas()
                time.sleep(0.1)
            if chave in _resumos:
                PASTA_DADOS.mkdir(parents=True, exist_ok=True)
                self._arq_resumo.write_bytes(_resumos.pop(chave))
        except Exception:  # noqa: BLE001
            pass

    def _executar(self):
        h = None
        try:
            lt = _biblioteca()
            if self.por_tipo:
                self.pasta = os.path.join(self.pasta, "Torrents")
                self.por_tipo = False
            os.makedirs(self.pasta, exist_ok=True)
            ses = sessao()
            aplicar_limite()
            with _lock:
                h = ses.add_torrent(self._parametros())
            self._h = h
            for par in self.pares_extras:
                h.connect_peer(par)
            self.etapa = "Procurando quem tem o arquivo…"
            self.status = CONECTANDO
            ult_resumo = time.monotonic()
            while not self._parar.is_set():
                with _lock:
                    _coletar_alertas()
                aplicar_limite()
                s = h.status()
                if s.errc.value():
                    raise IOError(s.errc.message())
                if s.has_metadata:
                    if not self.caminho:
                        self.nome = nome_seguro(s.name) if s.name else self.nome
                        self.caminho = os.path.join(self.pasta, s.name)
                    self.tamanho = s.total_wanted
                    self.baixado = s.total_wanted_done
                    self._pecas = list(s.pieces)
                self._pares = s.num_peers
                self.velocidade = float(s.download_rate)
                if s.state in (lt.torrent_status.checking_files, lt.torrent_status.checking_resume_data):
                    self.etapa = "Conferindo o que já foi baixado…"
                elif not s.has_metadata:
                    self.etapa = "Buscando as informações do torrent…"
                else:
                    self.etapa = "" if s.num_peers else "Procurando quem tem o arquivo…"
                    self.status = BAIXANDO
                if s.has_metadata and (s.is_finished or s.is_seeding) and s.state not in (
                        lt.torrent_status.checking_files, lt.torrent_status.checking_resume_data):
                    break
                if time.monotonic() - ult_resumo > 30 and s.has_metadata:
                    self._salvar_resumo(h, 2)
                    ult_resumo = time.monotonic()
                self._parar.wait(0.5)
            self.velocidade = 0.0
            self._pares = 0
            self.etapa = ""
            if self._parar.is_set():
                self._salvar_resumo(h)
                self.status = PAUSADO
            else:
                h.flush_cache() if hasattr(h, "flush_cache") else None
                self.baixado = self.tamanho or self.baixado
                self.concluido_em = time.time()
                for f in (self._arq_resumo, self._arq_torrent):
                    try:
                        f.unlink()
                    except OSError:
                        pass
                self.status = CONCLUIDO
        except Exception as e:  # noqa: BLE001
            self.velocidade = 0.0
            self.etapa = ""
            self.erro = str(e) or e.__class__.__name__
            self.status = PAUSADO if self._parar.is_set() else ERRO
        finally:
            self._h = None
            if h is not None:
                try:
                    with _lock:
                        sessao().remove_torrent(h)      # mantém os arquivos; para de compartilhar
                except Exception:  # noqa: BLE001
                    pass

    def apagar_parciais(self):
        """Remove o que foi baixado de um torrent não concluído (arquivo ou pasta) e os dados de retomada."""
        import shutil
        if self.caminho and os.path.normpath(self.caminho) != os.path.normpath(self.pasta):
            if os.path.isdir(self.caminho):
                shutil.rmtree(self.caminho, ignore_errors=True)
            elif os.path.exists(self.caminho):
                try:
                    os.remove(self.caminho)
                except OSError:
                    pass
        for f in (self._arq_resumo, self._arq_torrent):
            try:
                f.unlink()
            except OSError:
                pass


__all__ = ["DownloadTorrent", "eh_torrent", "disponivel", "aplicar_limite", "sessao"]
