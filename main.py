"""Convergio — ponto de entrada.

  Convergio.exe [link]                  abre o programa (e adiciona o link, se informado)
  Convergio.exe --selftest saida.txt    autoteste (usado na publicação)
  Convergio.exe --run-update <inst> <pid>   uso interno da atualização automática
"""
import sys


def main():
    argv = sys.argv
    if "--run-update" in argv:
        from convergio.atualizador import ajudante_atualizacao
        return ajudante_atualizacao(argv)
    if "--selftest" in argv:
        from convergio.selftest import executar
        return executar(argv)

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
    j = Janela()
    j.show()
    from urllib.parse import unquote
    for a in argv[1:]:
        if a.lower().startswith("convergio:"):          # protocolo convergio:<link>
            a = unquote(a[len("convergio:"):].lstrip("/"))
        if RE_URL.match(a):
            j.adicionar(a)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
