"""Depois do download: conferir a integridade (hash) e, se a pessoa ligar, verificar com o antivírus do Windows.

Hash: SHA-256 / SHA-1 / MD5. Se o servidor informou o hash (cabeçalhos Digest, Content-MD5 ou x-goog-hash) ou a
pessoa colou o hash esperado, a conferência é automática.
Antivírus: Microsoft Defender pela linha de comando (MpCmdRun.exe). Se encontrar ameaça, o próprio Defender põe o
arquivo em quarentena; o Convergio só avisa.
"""
from __future__ import annotations

import base64
import binascii
import glob
import hashlib
import os
import re
import subprocess
import sys
import threading

SEM_JANELA = 0x08000000 if sys.platform == "win32" else 0
ALGORITMOS = {32: "md5", 40: "sha1", 64: "sha256", 128: "sha512"}
RE_HEX = re.compile(r"\b([0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64}|[0-9a-fA-F]{128})\b")


def calcular(caminho: str, algoritmos=("sha256", "md5"), parar: threading.Event | None = None,
             progresso=None) -> dict[str, str]:
    hs = {a: hashlib.new(a) for a in algoritmos}
    total = os.path.getsize(caminho) or 1
    lido = 0
    with open(caminho, "rb") as f:
        while True:
            if parar is not None and parar.is_set():
                raise InterruptedError
            bloco = f.read(4 * 1024 * 1024)
            if not bloco:
                break
            for h in hs.values():
                h.update(bloco)
            lido += len(bloco)
            if progresso:
                progresso(lido / total)
    return {a: h.hexdigest() for a, h in hs.items()}


def hash_esperado(texto: str) -> tuple[str, str] | None:
    """(algoritmo, hash) encontrado num texto colado (aceita "sha256: …", linhas de arquivo .sha256 etc.)."""
    m = RE_HEX.search(texto or "")
    if not m:
        return None
    h = m.group(1).lower()
    return ALGORITMOS[len(h)], h


def hash_do_servidor(cabecalhos, parcial: bool = False) -> tuple[str, str] | None:
    """Hash do arquivo inteiro informado pelo servidor nos cabeçalhos (quando existe).
    Em respostas parciais (206) o Content-MD5 é só do trecho, então é ignorado."""
    def b64hex(v):
        try:
            return binascii.hexlify(base64.b64decode(v.strip())).decode()
        except (binascii.Error, ValueError):
            return None
    dig = cabecalhos.get("Repr-Digest") or ("" if parcial else cabecalhos.get("Digest") or "")
    for parte in dig.split(","):
        nome, _, valor = parte.strip().partition("=")
        nome = nome.lower().replace("-", "")
        valor = valor.strip(":")
        if nome in ("sha256", "sha512", "md5", "sha") and valor:
            hx = b64hex(valor)
            if hx and len(hx) in ALGORITMOS:
                return ALGORITMOS[len(hx)], hx
    md5 = None if parcial else cabecalhos.get("Content-MD5")
    if md5:
        hx = b64hex(md5)
        if hx and len(hx) == 32:
            return "md5", hx
    goog = cabecalhos.get("x-goog-hash") or ""
    m = re.search(r"md5=([A-Za-z0-9+/=]+)", goog)
    if m:
        hx = b64hex(m.group(1))
        if hx and len(hx) == 32:
            return "md5", hx
    return None


def conferir(caminho: str, algoritmo: str, esperado: str, parar=None) -> bool:
    return calcular(caminho, (algoritmo,), parar)[algoritmo] == esperado.lower()


# ------------------------------------------------------------------ antivírus
def mpcmdrun() -> str | None:
    """Caminho do MpCmdRun.exe do Microsoft Defender (a versão mais nova da plataforma, se houver)."""
    if sys.platform != "win32":
        return None
    pd = os.environ.get("ProgramData", r"C:\ProgramData")
    plataformas = sorted(glob.glob(os.path.join(pd, "Microsoft", "Windows Defender", "Platform", "*", "MpCmdRun.exe")))
    cands = plataformas[::-1] + [os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                                               "Windows Defender", "MpCmdRun.exe")]
    return next((c for c in cands if os.path.exists(c)), None)


def antivirus_disponivel() -> bool:
    return mpcmdrun() is not None


def verificar_antivirus(caminho: str, timeout: int = 900) -> tuple[str, str]:
    """("limpo" | "ameaca" | "erro", detalhe)."""
    exe = mpcmdrun()
    if not exe:
        return "erro", "Microsoft Defender não encontrado (outro antivírus pode estar em uso)"
    try:
        r = subprocess.run([exe, "-Scan", "-ScanType", "3", "-File", os.path.abspath(caminho)],
                           capture_output=True, text=True, timeout=timeout, creationflags=SEM_JANELA,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return "erro", "a verificação demorou demais"
    except OSError as e:
        return "erro", str(e)
    saida = (r.stdout or "") + (r.stderr or "")
    if r.returncode == 0:
        return "limpo", "nenhuma ameaça encontrada"
    if r.returncode == 2 or re.search(r"Threat\s+:|found \d+ threats", saida, re.I):
        m = re.search(r"Threat\s+:\s*(.+)", saida)
        return "ameaca", (m.group(1).strip() if m else "ameaça encontrada")
    return "erro", f"o Defender não conseguiu verificar (código {r.returncode})"


# ------------------------------------------------------------------ depois do download
def processar(d, antivirus: bool, ao_terminar=None):
    """Roda em segundo plano para um download concluído; o resultado fica em d.verif e aparece no status."""
    def trabalho():
        caminho = d.caminho
        if not caminho or not os.path.isfile(caminho):
            return
        esperado = getattr(d, "hash_esperado", None)
        if esperado:
            d.verif["hash"] = "conferindo"
            try:
                ok = conferir(caminho, *esperado)
                d.verif["hash"] = "ok" if ok else "diferente"
            except (OSError, InterruptedError):
                d.verif.pop("hash", None)
        if antivirus:
            d.verif["av"] = "verificando"
            res, det = verificar_antivirus(caminho)
            d.verif["av"] = res
            d.verif["av_detalhe"] = det
        if ao_terminar:
            ao_terminar(d)
    if not hasattr(d, "verif"):
        d.verif = {}
    threading.Thread(target=trabalho, daemon=True).start()


def texto_status(d) -> str:
    v = getattr(d, "verif", None) or {}
    partes = []
    h = v.get("hash")
    if h == "conferindo":
        partes.append("conferindo hash…")
    elif h == "ok":
        partes.append("✓ íntegro")
    elif h == "diferente":
        partes.append("⚠ hash diferente")
    a = v.get("av")
    if a == "verificando":
        partes.append("verificando vírus…")
    elif a == "limpo":
        partes.append("✓ sem vírus")
    elif a == "ameaca":
        partes.append("⚠ ameaça encontrada")
    return " · ".join(partes)


__all__ = ["calcular", "hash_esperado", "hash_do_servidor", "conferir", "antivirus_disponivel",
           "verificar_antivirus", "processar", "texto_status"]
