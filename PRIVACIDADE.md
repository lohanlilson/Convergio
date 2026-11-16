# Política de privacidade — Convergio e extensão Convergio

O Convergio é um acelerador de downloads que roda inteiramente no seu computador.

- **Nenhum dado é enviado ao desenvolvedor nem a terceiros.** Não há contas, anúncios, rastreamento ou telemetria.
- A extensão do navegador envia os dados do download que você iniciou (endereço do arquivo, nome, tamanho,
  página de origem e os cookies daquele site, necessários para sites com login) **apenas para o programa
  Convergio instalado no mesmo computador**, pelo endereço local `127.0.0.1:47851`.
- Para encontrar vídeos, a extensão observa os endereços e os tipos das respostas da aba aberta. Essa lista
  fica só na memória do navegador, é apagada ao trocar de página e não é enviada a lugar nenhum; só o vídeo
  que você mandar baixar é passado ao programa.
- O programa usa esses dados somente para baixar o arquivo que você pediu. A lista de downloads fica salva
  no seu computador, em `%APPDATA%\Convergio`.
- O programa acessa a internet para baixar os arquivos que você escolheu e para consultar, no GitHub, se
  existe uma versão nova do Convergio e, na primeira vez que um vídeo em streaming é baixado, para obter o
  conversor FFmpeg no PyPI.
- **Torrents:** ao baixar um torrent ou link magnet, o programa se conecta a outras pessoas que têm o mesmo
  arquivo (rede BitTorrent, DHT e descoberta na rede local). Isso é próprio do BitTorrent: essas pessoas veem o
  seu endereço IP enquanto o download acontece. O Convergio para de compartilhar quando o download termina.
- **Velocidade inteligente** (só se você ligar): para medir o ping, o programa abre conexões rápidas com
  servidores públicos de DNS (Cloudflare 1.1.1.1, Google 8.8.8.8, Quad9 9.9.9.9), sem enviar dados. Para saber
  se há uma chamada, consulta no registro do Windows se algum programa está usando o microfone (não ouve nada);
  para jogos, pergunta ao Windows se há um programa em tela cheia.
- **Antivírus** (só se você ligar): o arquivo baixado é verificado pelo Microsoft Defender do próprio Windows.

Contato: Lohan Lilson S. Lopes — lohanlilson@gmail.com
