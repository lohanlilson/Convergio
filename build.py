"""Gera o executável e o instalador do Convergio.

  python build.py              executável + instalador
  python build.py --publicar   também gera versao.json e NOTAS.md (para a Release do GitHub)

A versão vem de convergio/__init__.py (__version__). Saída na pasta Saida/.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(ROOT, "dist", "Convergio")
BUILD = os.path.join(ROOT, "build")
SAIDA = os.path.join(ROOT, "Saida")


def meta():
    src = open(os.path.join(ROOT, "convergio", "__init__.py"), encoding="utf-8").read()
    return dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', src, re.M))


def etapa(msg):
    print(f"\n=== {msg} ===", flush=True)


def arquivo_versao(ver):
    m = meta()
    t = tuple(([int(x) for x in re.findall(r"\d+", ver)] + [0] * 4)[:4])
    conteudo = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', '{m["AUTHOR"]}'),
    StringStruct('LegalCopyright', '© 2026 {m["AUTHOR"]} - {m["EMAIL"]}'),
    StringStruct('FileDescription', 'Convergio - acelerador de downloads'),
    StringStruct('FileVersion', '{ver}'),
    StringStruct('InternalName', 'Convergio'),
    StringStruct('OriginalFilename', 'Convergio.exe'),
    StringStruct('ProductName', 'Convergio'),
    StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [0x0416, 1200])])]
)"""
    os.makedirs(BUILD, exist_ok=True)
    caminho = os.path.join(BUILD, "version_info.txt")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


def pyinstaller(ver):
    etapa(f"Gerando executável (versão {ver})")
    sep = ";" if os.name == "nt" else ":"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
           "--name", "Convergio", "--icon", os.path.join(ROOT, "assets", "convergio.ico"),
           "--version-file", arquivo_versao(ver),
           "--add-data", f"{os.path.join(ROOT, 'assets')}{sep}assets",
           "--distpath", "dist", "--workpath", os.path.join("build", "pyi"), "--specpath", "build",
           "--exclude-module", "tkinter", "--exclude-module", "PySide6.QtWebEngineCore",
           "--exclude-module", "PySide6.QtWebEngineWidgets", "--exclude-module", "PySide6.Qt3DCore",
           "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtQml",
           "--exclude-module", "PySide6.QtMultimedia", "--exclude-module", "PySide6.QtCharts",
           os.path.join(ROOT, "main.py")]
    subprocess.run(cmd, cwd=ROOT, check=True)


def achar_iscc():
    cands = [shutil.which("ISCC"), shutil.which("iscc")]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Inno Setup 6", "ISCC.exe"),
                      os.path.join(base, "Programs", "Inno Setup 6", "ISCC.exe")]
    return next((c for c in cands if c and os.path.exists(c)), None)


def instalador(ver):
    etapa("Gerando instalador")
    exe = achar_iscc()
    if not exe:
        sys.exit("\nERRO: Inno Setup 6 não encontrado. Instale em https://jrsoftware.org/isdl.php e rode de novo.")
    m = meta()
    subprocess.run([exe, f"/DAppVersion={ver}", f"/DSourceDir={DIST}", f"/DAppPublisher={m['AUTHOR']}",
                    f"/DAppEmail={m['EMAIL']}", os.path.join(ROOT, "installer", "convergio.iss")],
                   cwd=os.path.join(ROOT, "installer"), check=True)


def notas(ver):
    """Texto da seção '## <versão>' do CHANGELOG.md."""
    txt = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    m = re.search(rf"^##\s*\[?{re.escape(ver)}\]?.*?$(.*?)(?=^##\s|\Z)", txt, re.M | re.S)
    return (m.group(1).strip() if m else "") or "Melhorias e correções."


def sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def publicar(ver):
    """versao.json (lido pelo programa para a atualização automática) e NOTAS.md (texto da Release)."""
    etapa("Gerando arquivos de publicação")
    repo = os.environ.get("GITHUB_REPOSITORY") or meta()["UPDATE_REPO"]
    setup = f"Convergio-Setup-{ver}.exe"
    p = os.path.join(SAIDA, setup)
    info = {"versao": ver, "data": datetime.date.today().isoformat(), "novidades": notas(ver),
            "instalador": {"url": f"https://github.com/{repo}/releases/download/v{ver}/{setup}",
                           "sha256": sha256(p), "tamanho": os.path.getsize(p)}}
    with open(os.path.join(SAIDA, "versao.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    with open(os.path.join(SAIDA, "NOTAS.md"), "w", encoding="utf-8") as f:
        f.write(info["novidades"] + f"\n\n**Instalação nova:** baixe `{setup}`. "
                "Quem já tem o programa recebe o aviso de atualização automaticamente.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-instalador", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    a = ap.parse_args()
    ver = meta()["__version__"]
    shutil.rmtree(SAIDA, ignore_errors=True)
    pyinstaller(ver)
    if not a.sem_instalador:
        instalador(ver)
        if a.publicar:
            publicar(ver)
    etapa("Concluído")
    print(r"Executável:  dist\Convergio\Convergio.exe")
    if os.path.isdir(SAIDA):
        for f in sorted(os.listdir(SAIDA)):
            print(f"Saída:       Saida\\{f}")


if __name__ == "__main__":
    main()
