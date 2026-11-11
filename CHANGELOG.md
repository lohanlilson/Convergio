# Novidades do Convergio

## 1.1.3
- **Atualização mais robusta:** antes de copiar, o instalador fecha qualquer processo que esteja rodando de dentro da pasta do Convergio e libera arquivos que continuem em uso, em vez de desfazer a instalação.
- As próximas atualizações **mostram o erro na tela**, com a opção de tentar de novo, se algo impedir a instalação.

## 1.1.2
- **Extensão corrigida:** com o navegador configurado para perguntar onde salvar, o download ficava parado e não começava nem no navegador nem no Convergio. Agora a extensão decide antes da janela "Salvar como": se o Convergio estiver aberto, o download vai direto para ele; se não, o navegador segue normalmente.
- **Depois de atualizar, recarregue a extensão** em `chrome://extensions` (botão ↻ no cartão do Convergio) ou reinicie o navegador.

## 1.1.1
- **Atualização automática corrigida:** o instalador agora fecha o Convergio sozinho antes de copiar os arquivos, em vez de desistir ou desfazer a instalação. Se algo impedir a atualização (por exemplo, o antivírus), o programa mostra o motivo ao abrir e oferece instalar manualmente.
- **Segundo plano desde a primeira vez:** o X manda o Convergio para perto do relógio do Windows; para fechar de vez, use **Sair** no menu do ícone.
- Na primeira vez, o programa pergunta se deve **iniciar com o Windows** (em silêncio, só em segundo plano).

## 1.1.0
- **Captura de downloads dos navegadores** (Chrome, Edge, Brave e Opera) pela extensão do Convergio: o download vai direto para o programa, com os cookies da sessão (sites com login também funcionam). Se o Convergio estiver fechado, o navegador baixa normalmente.
- Janela "Download capturado" para escolher o nome e a pasta (dá para desligar em Navegadores › Perguntar antes de baixar).
- Botão direito num link › **Baixar com o Convergio**.
- **Segundo plano:** ao clicar em fechar, o programa pergunta se deve continuar perto do relógio do Windows ou fechar de vez (a escolha pode ser lembrada).
- Menu no ícone perto do relógio: abrir, baixar o link copiado, pausar/retomar todos, abrir a pasta, ligar/desligar a captura, iniciar com o Windows, verificar atualizações e sair.
- Inicia com o Windows já em segundo plano (Opções › Iniciar com o Windows).
- Se o Convergio já estiver aberto, abrir de novo só traz a janela para a frente.

## 1.0.1
- Ícone novo: os feixes de luz violeta, azul e dourado (as conexões) convergem numa seta de download de vidro.
- Instalador com as imagens da nova identidade visual.

## 1.0.0
- Primeira versão do **Convergio**, acelerador de downloads.
- Até 32 conexões por arquivo com **segmentação dinâmica**: quando uma conexão termina o seu trecho, assume metade do maior trecho que ainda falta.
- Pausar e retomar, inclusive depois de fechar o programa.
- Reconexão automática quando a conexão cai.
- Fila de downloads simultâneos e captura de links copiados.
- Barra de conexões mostrando cada trecho sendo baixado.
- Temas claro e escuro (ou o do Windows).
- Atualização automática pelo GitHub.
