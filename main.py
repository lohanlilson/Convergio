"""Convergio — ponto de entrada.

  Convergio.exe [link]                  abre o programa (e adiciona o link, se informado)
  Convergio.exe --minimizado            inicia só na bandeja (usado ao iniciar com o Windows)
  Convergio.exe --selftest saida.txt    autoteste (usado na publicação)
  Convergio.exe --run-update <inst> <pid>   uso interno da atualização automática
"""
import sys


def _limpar_sobras_de_atualizacao():
    """Apaga arquivos *.antigo que o instalador renomeou por estarem em uso durante uma atualização."""
    import os
    for raiz, _, arquivos in os.walk(os.path.dirname(sys.executable)):
        for nome in arquivos:
            if nome.endswith(".antigo"):
                try:
                    os.remove(os.path.join(raiz, nome))
                except OSError:
                    pass


def main():
    argv = sys.argv
    if "--run-update" in argv:
        from convergio.atualizador import ajudante_atualizacao
        return ajudante_atualizacao(argv)
    if "--selftest" in argv:
        from convergio.selftest import executar
        return executar(argv)

    from urllib.parse import unquote
    links = []
    for a in argv[1:]:
        if a.lower().startswith("convergio:"):          # protocolo convergio:<link>
            a = unquote(a[len("convergio:"):].lstrip("/"))
        if a.lower().startswith(("http://", "https://")):
            links.append(a)

    # instância única: se já estiver aberto, entrega os links (ou só mostra a janela) e encerra
    from convergio.integracao import entregar_a_instancia_aberta, instancia_aberta
    if "--minimizado" in argv:
        if instancia_aberta():
            return 0
    elif entregar_a_instancia_aberta(links):
        return 0

    if getattr(sys, "frozen", False):
        _limpar_sobras_de_atualizacao()

    if sys.platform == "win32":
        import ctypes
        # o instalador usa esse mutex para saber se o programa está aberto
        ctypes.windll.kernel32.CreateMutexW(None, False, "Convergio_Running")
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Convergio.App")

    from PySide6.QtWidgets import QApplication
    from convergio import APP_NAME, tema
    from convergio.janela import RE_URL, Janela, icone_app

    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(icone_app())
    from PySide6.QtCore import QSettings
    escolha = QSettings("Convergio", "Convergio").value("tema", "auto")
    tema.aplicar(app, tema.sistema_escuro() if escolha == "auto" else escolha == "escuro")
    app.setQuitOnLastWindowClosed(False)              # continua rodando na bandeja
    j = Janela()
    if "--minimizado" not in argv:
        j.show()
    for a in links:
        if RE_URL.match(a):
            j.adicionar(a)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
