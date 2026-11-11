<p align="center"><img src="assets/logo.png" width="128" alt="Convergio"></p>

<h1 align="center">Convergio</h1>
<p align="center"><b>Acelerador de downloads para Windows — várias conexões, um arquivo.</b></p>

<p align="center">
  <a href="https://github.com/lohanlilson/Convergio/releases/latest/download/Convergio-Setup.exe"><b>⬇ Baixar o instalador</b></a>
</p>

O Convergio divide cada arquivo em vários trechos e baixa todos ao mesmo tempo, como o IDM. É útil sobretudo
com servidores que limitam a velocidade de cada conexão.

## Recursos

- **Até 32 conexões por arquivo**, com **segmentação dinâmica**: quando uma conexão termina o seu trecho, ela
  assume metade do maior trecho que ainda falta. Assim nenhuma conexão fica parada no fim do download.
- **Reaproveitamento de conexões** (keep-alive) entre um trecho e outro.
- **Pausar e retomar**, inclusive depois de fechar o programa ou desligar o computador.
- **Reconexão automática** quando a conexão cai, redistribuindo os trechos.
- Servidores sem suporte a download em partes são baixados com uma conexão só.
- Fila de downloads simultâneos, captura de links copiados e barra com os trechos de cada conexão.
- Temas claro e escuro, na mesma identidade visual do [Dispersio PDF](https://github.com/lohanlilson/DispersioPDF).
- **Atualização automática**: o programa avisa quando sai uma versão nova e se atualiza sozinho.
- **Captura de downloads dos navegadores** (Chrome, Edge, Brave, Opera) pela extensão em [`extensao/`](extensao),
  levando os cookies da sessão. Se o Convergio estiver fechado, o navegador baixa normalmente.
- Fica em **segundo plano** perto do relógio do Windows, com menu de atalhos, e pode iniciar com o Windows.
- Protocolo `convergio:<link>`, que permite enviar downloads de outros programas.

## Extensão do navegador

O instalador copia a extensão para `C:\Program Files\Convergio\extensao`. Para instalar no navegador:

1. Abra `chrome://extensions` (no Edge, `edge://extensions`).
2. Ative o **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta `extensao`.

O programa se comunica com a extensão só pela própria máquina (`127.0.0.1:47851`) e recusa pedidos de páginas da web.

## Executar pelo código-fonte

```bat
pip install -r requirements.txt
python main.py
```

## Gerar o instalador

Requer o [Inno Setup 6](https://jrsoftware.org/isdl.php).

```bat
build.bat
```

O instalador é gerado em `Saida\`.

## Publicar uma versão

1. Aumente `__version__` em `convergio/__init__.py` e descreva as novidades no `CHANGELOG.md` (`## 1.0.1`).
2. Envie para a branch `main`.

O GitHub Actions (`.github/workflows/publicar.yml`) gera o executável e o instalador num servidor Windows,
roda os autotestes (no código, no executável e no programa instalado) e publica a Release com o `versao.json`.
O Convergio instalado detecta a nova versão sozinho.

---

© 2026 Lohan Lilson S. Lopes
