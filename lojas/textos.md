# Textos para a página da loja

**Nome:** Convergio — downloads acelerados

**Descrição curta (até 132 caracteres):**
Envia os downloads do navegador para o Convergio, acelerador de downloads gratuito para Windows.

**Descrição:**
Esta extensão integra o navegador ao Convergio, um acelerador de downloads gratuito e de código aberto para
Windows. Com ela, os downloads que você inicia no navegador são baixados pelo Convergio com várias conexões
ao mesmo tempo, com pausar e retomar.

- Captura automática dos downloads (com um tamanho mínimo configurável).
- Botão direito num link: "Baixar com o Convergio".
- Funciona em sites com login: os cookies do site vão junto com o download.
- Encontra os vídeos da página (streaming HLS e arquivos de vídeo) e mostra um botão "Baixar" no ícone da extensão.
  Não baixa do YouTube nem vídeos protegidos contra cópia.
- Se o Convergio não estiver aberto, o navegador baixa normalmente.

A extensão precisa do programa Convergio instalado: https://github.com/lohanlilson/Convergio
Ela conversa só com o programa no seu próprio computador (127.0.0.1) e não envia dados a ninguém.

**Categoria:** Produtividade

**Justificativa das permissões:**
- `downloads`: identificar os downloads iniciados e passá-los ao Convergio.
- `cookies` e acesso aos sites: enviar ao Convergio (no mesmo computador) os cookies do site do arquivo,
  necessários para baixar arquivos de sites com login.
- `contextMenus`: item "Baixar com o Convergio" no botão direito.
- `storage`: guardar as opções da extensão.
- `notifications`: avisar quando o Convergio não está aberto.
- `webRequest`, `webNavigation` e `tabs`: observar (sem alterar) as respostas da aba para encontrar vídeos,
  limpar a lista ao trocar de página e usar o título da aba como nome do arquivo.
- `alarms`: avisar o programa, uma vez por minuto, de que o navegador está vinculado.
