"""Abre o Convergio instalado, clica em "Atualizar agora" e registra processos e janelas a cada 2 s."""
import subprocess
import time

from pywinauto import Desktop

EXE = r"C:\Program Files\Convergio\Convergio.exe"


def processos():
    out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True).stdout
    return [l.split('","')[0].strip('"') + "#" + l.split('","')[1] for l in out.splitlines()
            if "Convergio" in l or ".tmp" in l.lower()]


def janelas():
    try:
        return [w.window_text() for w in Desktop(backend="uia").windows() if w.window_text()]
    except Exception as e:  # noqa: BLE001
        return [f"(erro ao listar janelas: {e})"]


app = subprocess.Popen([EXE])
print("programa aberto, PID", app.pid, flush=True)
dlg = None
for _ in range(40):
    time.sleep(1)
    try:
        w = Desktop(backend="uia").window(title_re="Atualização do Convergio.*")
        if w.exists():
            dlg = w
            break
    except Exception:  # noqa: BLE001
        pass
if not dlg:
    print("a janela de atualização não apareceu; janelas:", janelas())
    raise SystemExit(1)
print("janela de atualização apareceu:", dlg.window_text(), flush=True)
dlg.child_window(title="Atualizar agora", control_type="Button").click_input()
print("clicou em Atualizar agora", flush=True)
t0 = time.time()
while time.time() - t0 < 240:
    time.sleep(2)
    print(f"{time.time() - t0:5.0f}s  principal_vivo={app.poll() is None}  proc={processos()}  janelas={janelas()}",
          flush=True)
