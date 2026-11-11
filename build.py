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


def arvore(pasta):
    """{caminho relativo: sha256} de uma pasta instalada (sem o desinstalador e sobras)."""
    saida = {}
    for raiz, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            if nome.lower().startswith("unins") or nome.endswith(".antigo"):
                continue
            c = os.path.join(raiz, nome)
            saida[os.path.relpath(c, pasta).replace("\\", "/")] = sha256(c)
    return saida


def arvore_nova():
    """{caminho relativo: caminho real} do que o instalador completo coloca na pasta do programa."""
    saida = {}
    for origem, prefixo in ((DIST, ""), (os.path.join(ROOT, "extensao"), "extensao/")):
        for raiz, _, arquivos in os.walk(origem):
            for nome in arquivos:
                c = os.path.join(raiz, nome)
                saida[prefixo + os.path.relpath(c, origem).replace("\\", "/")] = c
    return saida


def patch(ver, base_dir, base_ver):
    """Instalador pequeno só com os arquivos que mudaram desde a versão anterior."""
    etapa(f"Gerando atualização pequena {base_ver} -> {ver}")
    antigos, novos = arvore(base_dir), arvore_nova()
    mudados = [rel for rel, c in novos.items() if antigos.get(rel) != sha256(c)]
    removidos = [rel for rel in antigos if rel not in novos]
    preparo = os.path.join(BUILD, "patch")
    shutil.rmtree(preparo, ignore_errors=True)
    for rel in mudados:
        destino = os.path.join(preparo, rel)
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        shutil.copy2(novos[rel], destino)
    with open(os.path.join(BUILD, "patch_remover.iss"), "w", encoding="utf-8-sig") as f:
        f.write("[InstallDelete]\n")
        for rel in removidos:
            f.write('Type: files; Name: "{app}\\%s"\n' % rel.replace("/", "\\"))
    total = sum(os.path.getsize(novos[r]) for r in mudados)
    print(f"{len(mudados)} arquivo(s) mudaram ({total / 1048576:.1f} MB), {len(removidos)} removido(s), "
          f"{len(novos) - len(mudados)} iguais")
    m = meta()
    subprocess.run([achar_iscc(), f"/DAppVersion={ver}", f"/DBaseVersion={base_ver}", f"/DSourceDir={preparo}",
                    f"/DAppPublisher={m['AUTHOR']}", os.path.join(ROOT, "installer", "patch.iss")],
                   cwd=os.path.join(ROOT, "installer"), check=True)
    return f"Convergio-Atualizacao-{base_ver}-para-{ver}.exe"


def conferir(pasta):
    """Confere se uma pasta instalada está idêntica ao que o instalador completo desta versão coloca."""
    instalado, novos = arvore(pasta), arvore_nova()
    diferentes = [r for r, c in novos.items() if instalado.get(r) != sha256(c)]
    sobrando = [r for r in instalado if r not in novos]
    for r in diferentes[:20]:
        print("DIFERENTE ou faltando:", r)
    for r in sobrando[:20]:
        print("SOBRANDO:", r)
    print(f"Conferência: {len(novos)} arquivos, {len(diferentes)} diferentes, {len(sobrando)} sobrando")
    return not diferentes and not sobrando


def publicar(ver, arquivo_patch=None, base_ver=None):
    """versao.json (lido pelo programa para a atualização automática) e NOTAS.md (texto da Release)."""
    etapa("Gerando arquivos de publicação")
    repo = os.environ.get("GITHUB_REPOSITORY") or meta()["UPDATE_REPO"]
    setup = f"Convergio-Setup-{ver}.exe"
    p = os.path.join(SAIDA, setup)
    info = {"versao": ver, "data": datetime.date.today().isoformat(), "novidades": notas(ver),
            "instalador": {"url": f"https://github.com/{repo}/releases/download/v{ver}/{setup}",
                           "sha256": sha256(p), "tamanho": os.path.getsize(p)}}
    if arquivo_patch:
        c = os.path.join(SAIDA, arquivo_patch)
        info["patches"] = {base_ver: {"url": f"https://github.com/{repo}/releases/download/v{ver}/{arquivo_patch}",
                                      "sha256": sha256(c), "tamanho": os.path.getsize(c)}}
    # pacote da extensão para enviar às lojas (Edge Add-ons, Chrome Web Store)
    shutil.make_archive(os.path.join(SAIDA, "Convergio-extensao"), "zip", os.path.join(ROOT, "extensao"))
    with open(os.path.join(SAIDA, "versao.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    with open(os.path.join(SAIDA, "NOTAS.md"), "w", encoding="utf-8") as f:
        f.write(info["novidades"] + f"\n\n**Instalação nova:** baixe `{setup}`. "
                "Quem já tem o programa recebe o aviso de atualização automaticamente.\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sem-instalador", action="store_true")
    ap.add_argument("--publicar", action="store_true")
    ap.add_argument("--base-dir", help="pasta com a versão anterior instalada (gera a atualização pequena)")
    ap.add_argument("--base-versao")
    ap.add_argument("--conferir", help="só confere se a pasta instalada está idêntica a esta versão")
    a = ap.parse_args()
    ver = meta()["__version__"]
    if a.conferir:
        sys.exit(0 if conferir(a.conferir) else 1)
    shutil.rmtree(SAIDA, ignore_errors=True)
    pyinstaller(ver)
    if not a.sem_instalador:
        instalador(ver)
        arquivo_patch = None
        if a.base_dir and a.base_versao and os.path.isdir(a.base_dir) and a.base_versao != ver:
            arquivo_patch = patch(ver, a.base_dir, a.base_versao)
        if a.publicar:
            publicar(ver, arquivo_patch, a.base_versao)
    etapa("Concluído")
    print(r"Executável:  dist\Convergio\Convergio.exe")
    if os.path.isdir(SAIDA):
        for f in sorted(os.listdir(SAIDA)):
            print(f"Saída:       Saida\\{f}")


if __name__ == "__main__":
    main()
