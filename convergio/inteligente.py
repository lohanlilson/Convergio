"""Velocidade inteligente (opcional, desligada por padrão).

Enquanto há downloads, o Convergio observa três coisas e diminui a velocidade só quando precisa:
  • Internet lenta: mede o tempo de resposta (ping) da internet. Quando o download enche a conexão, o ping sobe
    (jogos travam, vídeo-chamada corta); aí a velocidade é reduzida aos poucos até o ping voltar ao normal.
  • Chamada: o microfone está em uso (Meet, Zoom, Teams, Discord, WhatsApp…).
  • Jogo / tela cheia: há um programa em tela cheia (jogo, apresentação, filme).
Nos dois últimos casos a velocidade fica limitada a uma porcentagem (escolhida pela pessoa) da velocidade normal.
Quando a situação passa, tudo volta à velocidade cheia. Nada sai do computador: o ping é só uma conexão rápida
a servidores públicos de DNS.
"""
from __future__ import annotations

import socket
import sys
import threading
import time

from .motor import LIMITADOR

ALVOS = (("1.1.1.1", 443), ("8.8.8.8", 443), ("9.9.9.9", 443))
PISO = 64 * 1024                  # nunca reduz abaixo disso (para o download não parar)


def medir_ping(timeout: float = 1.5) -> float | None:
    """Menor tempo (ms) para abrir uma conexão com servidores públicos; None sem internet."""
    melhor = None
    for host, porta in ALVOS:
        t0 = time.perf_counter()
        try:
            with socket.create_connection((host, porta), timeout=timeout):
                ms = (time.perf_counter() - t0) * 1000
        except OSError:
            continue
        melhor = ms if melhor is None else min(melhor, ms)
        if melhor < 60:
            break
    return melhor


def microfone_em_uso() -> bool:
    """Windows 10/11: algum programa está usando o microfone agora (registro de privacidade do Windows)."""
    if sys.platform != "win32":
        return False
    import winreg
    raiz = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone"

    def em_uso(chave) -> bool:
        i = 0
        while True:
            try:
                nome = winreg.EnumKey(chave, i)
            except OSError:
                return False
            i += 1
            try:
                with winreg.OpenKey(chave, nome) as sub:
                    if nome == "NonPackaged":
                        if em_uso(sub):
                            return True
                        continue
                    try:
                        parou, _ = winreg.QueryValueEx(sub, "LastUsedTimeStop")
                        comecou, _ = winreg.QueryValueEx(sub, "LastUsedTimeStart")
                    except OSError:
                        continue
                    if parou == 0 and comecou:
                        return True
            except OSError:
                continue
    for base in (winreg.HKEY_CURRENT_USER,):
        try:
            with winreg.OpenKey(base, raiz) as k:
                if em_uso(k):
                    return True
        except OSError:
            pass
    return False


def tela_cheia() -> bool:
    """Windows: um jogo (Direct3D) ou outro programa em tela cheia / modo apresentação."""
    if sys.platform != "win32":
        return False
    import ctypes
    estado = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(estado)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    # 2 = ocupado (tela cheia), 3 = Direct3D em tela cheia, 4 = modo apresentação
    return estado.value in (2, 3, 4)


class VelocidadeInteligente:
    """Controla LIMITADOR.automatico. Chame ajustar() a cada ~2 s (numa thread) enquanto há downloads."""

    def __init__(self):
        self.ping = True
        self.chamada = True
        self.jogo = True
        self.porcentagem = 30         # nos modos chamada/jogo
        self.ligado = False
        self.motivo = ""              # texto para a interface ("", "chamada", "jogo", "internet")
        self._base: float | None = None   # ping normal (sem download)
        self._amostras: list[float] = []
        self._pico = 0.0
        self._teto = 0.0              # velocidade em que o ping piorou da última vez
        self._teto_em = 0.0              # maior velocidade total recente (referência para a porcentagem)
        self._lock = threading.Lock()
        self.medir = medir_ping       # trocáveis nos testes
        self.mic = microfone_em_uso
        self.cheia = tela_cheia

    def desligar(self):
        self.ligado = False
        self.motivo = ""
        LIMITADOR.automatico = 0

    def calibrar(self):
        """Ping de referência, medido sem downloads ativos."""
        p = self.medir()
        if p is not None:
            self._base = p if self._base is None else min(self._base * 0.8 + p * 0.2, max(self._base, p))

    def ajustar(self, velocidade_total: float, baixando: bool):
        with self._lock:
            if not self.ligado or not baixando:
                LIMITADOR.automatico = 0
                self.motivo = ""
                if self.ligado and self.ping and not baixando:
                    self.calibrar()
                return
            if LIMITADOR.automatico == 0:             # referência: velocidade sem redução (esquece devagar)
                self._pico = max(velocidade_total, self._pico * 0.98)
            ref = max(self._pico, PISO * 4)

            motivo = ""
            if self.chamada and self.mic():
                motivo = "chamada"
            elif self.jogo and self.cheia():
                motivo = "jogo"
            if motivo:
                self.motivo = motivo
                LIMITADOR.automatico = int(max(PISO, ref * self.porcentagem / 100))
                return

            if self.ping:
                p = self.medir()
                if p is not None:
                    if self._base is None:
                        self._base = p
                    self._amostras = (self._amostras + [p])[-3:]
                    atual = sorted(self._amostras)[len(self._amostras) // 2]
                    limite_ms = max(self._base * 2.5, self._base + 80)
                    agora = time.monotonic()
                    if self._teto and agora - self._teto_em > 90:     # estável há um tempo: pode tentar mais
                        self._teto = 0.0
                    if atual > limite_ms:               # fila cheia no roteador: reduz 30%
                        base_vel = LIMITADOR.automatico or velocidade_total or ref
                        self._teto, self._teto_em = base_vel, agora
                        LIMITADOR.automatico = int(max(PISO, base_vel * 0.7))
                        self.motivo = "internet"
                        return
                    if LIMITADOR.automatico and atual < self._base + 40:     # normal: volta aos poucos (+15%)
                        novo = LIMITADOR.automatico * 1.15
                        if self._teto:
                            novo = min(novo, self._teto * 0.85)
                        if novo >= ref * 1.2:
                            LIMITADOR.automatico = 0
                            self.motivo = ""
                        else:
                            LIMITADOR.automatico = int(novo)
                            self.motivo = "internet"
                        return
                    if LIMITADOR.automatico:
                        self.motivo = "internet"
                        return
            LIMITADOR.automatico = 0
            self.motivo = ""

    def texto(self) -> str:
        return {"chamada": "🎙 Chamada em andamento — downloads mais lentos",
                "jogo": "🎮 Tela cheia — downloads mais lentos",
                "internet": "🐢 Internet ocupada — velocidade ajustada para não travar"}.get(self.motivo, "")


__all__ = ["VelocidadeInteligente", "medir_ping", "microfone_em_uso", "tela_cheia"]
