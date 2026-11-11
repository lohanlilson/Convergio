# Novidades do Convergio

## 1.2.0
- **Histórico:** os downloads concluídos ficam na lista, com data e hora, mesmo depois de fechar o programa.
- **Pastas por tipo:** vídeos, músicas, documentos, compactados, programas e imagens vão cada um para a sua subpasta (dá para desligar em Configurações › Downloads).
- **Limite de velocidade**, pelo menu Downloads, pelo ícone perto do relógio ou nas Configurações.
- **Agendamento:** iniciar e pausar os downloads em horários fixos, e fechar, suspender ou desligar o computador quando tudo terminar.
- **Atualizar link:** quando o link de um download expira, clique com o botão direito › Atualizar link e baixe de novo no navegador; o Convergio continua de onde parou.
- **Aviso ao terminar**, no canto da tela, com os botões Abrir e Abrir pasta.
- **Vários links de uma vez** (Arquivo › Adicionar vários links, colar uma lista ou arrastar links para a janela).
- **Menu do botão direito** na lista: abrir, mostrar na pasta, baixar de novo, copiar link, abrir a página de origem.
- **Tela de Configurações** única e tela **Navegadores**, que mostra os navegadores do computador e se cada um está vinculado.
- Depois de atualizar, recarregue a extensão em `chrome://extensions` (botão ↻).

## 1.1.5
- O aviso de "extensão desatualizada" não trava mais a janela do download.
- Se o navegador mandar um link que já está na lista (por exemplo, um que deu erro), o Convergio retoma esse download, com os cookies novos do navegador, e avisa; antes, não acontecia nada.
- Downloads que deram erro por nome de arquivo longo demais voltam a funcionar ao clicar em Retomar.

## 1.1.4
- Corrigido o erro "Invalid argument" em sites que usam um código enorme no lugar do nome do arquivo: o nome agora vem do servidor e, se for grande demais, é encurtado.
- A janela abre centralizada na tela.
- O Convergio avisa quando o navegador ainda usa uma versão antiga da extensão e mostra como recarregar.

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
