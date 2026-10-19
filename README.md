# Fácil: Coletor de Evidências Digitais Intuitivo

Ferramenta gratuita e de código aberto para coleta de evidências digitais no Windows 10 em diante, de autoria de
Elias Edenis.

**Situação:** versão 0.1.0 de teste, distribuída apenas a testadores convidados. Ainda não há build oficial
assinado, e o relatório gerado informa isso.

## Origem do projeto

O Fácil, com a arquitetura aqui descrita, foi idealizado por Elias Edenis e codificado com *vibecoding*
(programação em que o autor descreve em linguagem natural o comportamento desejado e uma inteligência artificial
escreve o código), incluindo testes severos de segurança. O projeto nasceu das necessidades constatadas no dia a
dia da investigação e dos riscos na coleta de evidências digitais identificados pelo profissional, riscos que
outras ferramentas de coleta local não cobrem.

O exemplo central é o DevTools (ferramentas de desenvolvedor, abertas pelo comando "inspecionar elemento"), presente
no navegador instalado em qualquer computador. Com ele, qualquer pessoa altera textos, nomes, números e imagens
exibidos numa página sem que nada mude no servidor de origem, e o print feito depois disso não se distingue de um
verdadeiro. Ferramentas que gravam o navegador comum do computador onde a coleta é feita não impedem essa
alteração. O Fácil usa um navegador próprio, em que o DevTools é fechado no mesmo instante em que é aberto e a
tentativa fica registrada no relatório; guarda o arquivo HAR, que é a via original do que o servidor entregou; e
registra automaticamente no relatório todo arquivo baixado durante a coleta.

## Funções e o problema que cada uma resolve

### Confiança da coleta

- **Carimbo do tempo na abertura e no fechamento.** O hash da coleta é enviado a autoridades independentes de
  carimbo do tempo (padrão RFC 3161), que atestam que aquele conteúdo existia naquele momento. A ferramenta busca
  carimbos de duas autoridades diferentes, para que a falha de uma não deixe a coleta sem testemunha externa. *Resolve:* um
  registro guardado só no computador pode ser refeito por quem controla a máquina; o carimbo é emitido por
  terceiro e delimita no tempo o início e o fim da coleta. Só o hash sai do computador, nunca o conteúdo.
- **Hash SHA-256 de cada arquivo e manifesto.** Cada arquivo recebe sua impressão digital matemática, e a lista
  de todas elas (o manifesto) é carimbada no fechamento. *Resolve:* prova que o arquivo juntado ao processo é
  exatamente o coletado; qualquer alteração, por menor que seja, muda o hash.
- **Log encadeado.** Cada ação da coleta vira um registro que contém o hash do anterior. *Resolve:* apagar,
  inserir ou editar uma etapa da coleta quebra a sequência e fica evidente.
- **Conferência da hora oficial.** A diferença entre o relógio do computador e servidores públicos de hora é
  medida e registrada, sem corrigir o relógio. *Resolve:* um relógio errado ou adulterado comprometeria todos os
  horários do relatório.
- **Registro do ambiente.** Documenta máquina virtual, acesso remoto ativo, privilégio de administrador e os
  programas em execução. *Resolve:* condições que interessam a quem avalia a prova, como uma coleta feita com
  outra pessoa controlando o computador à distância, ficam documentadas em vez de ocultas.
- **Privacidade.** Sem conta, cadastro ou telemetria; nada sai da máquina além do hash enviado ao carimbo do
  tempo. *Resolve:* permite o uso em casos sigilosos, sem expor o material a servidores de terceiros.

### Navegador protegido, para sites e WhatsApp Web

- **Navegador próprio e isolado.** Cada coleta abre um navegador novo, com perfil vazio apagado ao final, sem
  extensões e controlado por canal interno fechado a outros programas. *Resolve:* o navegador comum carrega
  extensões, histórico e dados de uso anterior que podem alterar as páginas exibidas.
- **Vigilância do DevTools.** Se as ferramentas de desenvolvedor forem abertas, a ferramenta as fecha no mesmo
  instante e registra a tentativa como alerta no quadro de confiabilidade do relatório. *Resolve:* impede a
  edição da página pelo "inspecionar elemento", que nenhum print consegue revelar depois.
- **Registro do tráfego em HAR.** Guarda cada requisição e resposta trocada com os servidores (endereços,
  horários, cabeçalhos e conteúdo), no formato padrão HAR. *Resolve:* o print mostra a tela, e o HAR mostra o que
  o servidor de fato enviou; a divergência entre os dois revela qualquer alteração feita na página exibida.
- **Registro automático de downloads.** Todo arquivo baixado durante a coleta é salvo, recebe hash e entra no
  relatório com o endereço de origem. *Resolve:* um arquivo baixado sem registro perde a ligação com o site de
  onde veio.
- **IP e certificado de cada página.** Registra o endereço numérico do servidor que respondeu e o certificado da
  conexão segura, e detecta quando antivírus ou proxy se colocam no meio da conexão. *Resolve:* nesses casos o
  certificado original do site não é visível, e o relatório deixa de afirmar "certificado válido" em vez de
  atestar algo que não conferiu.
- **Detecção de interferência de outros programas.** Aponta código inserido nas páginas por antivírus e
  bibliotecas de outros programas carregadas dentro do navegador. *Resolve:* alterações vindas de fora do
  navegador ficam registradas como alerta.
- **Gravação da janela inteira com som.** O vídeo mostra a barra de endereço e todo o conteúdo da janela, com
  data e hora em cada quadro, dividido em segmentos de até 10 MB, cada um com hash. *Resolve:* prints soltos
  permitem escolher só o que interessa; a gravação contínua mostra tudo o que aconteceu, e os segmentos respeitam o
  limite de juntada do PJe e do eproc.
- **Prints da página inteira e registro da navegação.** Prints com hash, histórico completo de páginas, abas,
  janelas e diálogos da sessão. *Resolve:* o relatório mostra todo o percurso, não apenas as páginas escolhidas.
- **Roteiro guiado do WhatsApp Web.** Pede ao usuário que mostre o perfil da conta e os dados do contato com o
  número de telefone visível, com print rotulado em cada passo. *Resolve:* o nome exibido no WhatsApp é o salvo
  no aparelho; a identificação confiável é o número.
- **Token de verificação.** Gera um código derivado do primeiro registro da coleta, que o usuário envia para a
  própria conta no WhatsApp. *Resolve:* prova que a conta exibida estava conectada e em uso durante a sessão
  carimbada, e não num registro montado antes, já que o código não existia antes da abertura da coleta.

### Gravação da tela

- **Tela inteira com o som do computador.** Grava o monitor escolhido e o som que sai pela caixa ou pelo fone,
  com fio, USB ou Bluetooth, sem configurar "mixagem estéreo" e sem trocar a saída de som. *Resolve:* registra o
  que acontece fora do navegador, como abrir pastas, executar arquivos e reproduzir áudios, sem a configuração de
  som que outras soluções exigem e que muitos computadores nem oferecem.
- **Teste de som.** Toca um tom curto e confere se ele foi captado, antes e durante a coleta. *Resolve:* evita
  descobrir só depois que a gravação ficou sem som.

### Arquivos, pendrives e e-mails

- **Coleta lógica de arquivos.** Lê as datas antes de abrir cada arquivo, calcula o hash na origem e na cópia e
  compara os dois; falhas são registradas arquivo a arquivo, sem interromper a coleta. *Resolve:* uma cópia
  comum pode alterar datas e não prova que é idêntica ao original.
- **Origem de arquivos baixados.** Lê a marca que o Windows grava em arquivos vindos da internet (o
  `Zone.Identifier`), com o endereço de onde foram baixados. *Resolve:* recupera a origem de um arquivo baixado
  antes da coleta.
- **Identificação da mídia de origem.** Registra número de série do volume, modelo e número de série do
  dispositivo, e alerta quando origem e destino estão na mesma unidade. *Resolve:* liga cada arquivo ao
  dispositivo de onde saiu.
- **Bloqueio de escrita em pendrive ou disco USB.** Antes da conexão, configura o Windows para recusar gravações
  em dispositivos USB, confere a configuração, mantém durante a cópia e restaura ao final. Opcional, e o único
  recurso que pede privilégio de administrador. *Resolve:* conectar um pendrive ao Windows pode gravar dados nele
  e alterar a evidência.
- **Análise de e-mail (.eml).** Preserva o arquivo original com hash e extrai remetente, destinatários, datas,
  anexos e o caminho percorrido entre servidores (cabeçalhos `Received`), sem acesso à internet. *Resolve:* o
  print de um e-mail não mostra por onde a mensagem passou, e o original preservado permite exame posterior por
  perito.

### Relatório e conferência

- **Relatório em PDF e HTML, e declaração editável.** Relatório em linguagem simples, que diz exatamente o que
  atesta e o que não atesta, com síntese, ficha por evidência e anexo técnico; declaração do operador em `.docx`
  vinculada à coleta pelo hash do manifesto. Se o PDF passar de 10 MB, é dividido em volumes. *Resolve:*
  relatórios técnicos costumam ser ilegíveis para delegados, promotores e juízes, e arquivos grandes não entram no
  PJe e no eproc.
- **Verificação independente.** Um comando confere o log encadeado, o manifesto e os carimbos do tempo de
  qualquer pasta de coleta. *Resolve:* qualquer perito confere a integridade sem precisar confiar no autor da
  ferramenta.
- **Guia de uso inicial.** Na primeira execução, explica em linguagem simples por que desativar
  temporariamente o antivírus e registra a escolha do usuário, sem bloquear nada. *Resolve:* antivírus
  costumam bloquear a gravação de tela e som e se colocar no meio das conexões seguras.

## Como instalar a versão de teste

Não é preciso instalar Python nem baixar nada além do pacote: ele já traz o navegador, o ffmpeg (programa que
monta os vídeos) e todas as bibliotecas.

1. Nesta página do repositório, abra **Releases** (coluna da direita) e baixe o arquivo `Facil-0.1.0-teste.1.zip`.
2. Clique com o botão direito no arquivo baixado, escolha **Extrair tudo** e extraia para uma pasta sua, por
   exemplo Documentos. Não execute de dentro do .zip.
3. Na pasta extraída, dê dois cliques em `Iniciar Facil.bat`.
4. Como o pacote de teste ainda não tem assinatura digital, o Windows pode mostrar "O Windows protegeu o
   computador". Clique em **Mais informações** e depois em **Executar assim mesmo**.

Requisitos: Windows 10 versão 1903 ou mais nova, de 64 bits, com o Microsoft Edge WebView2 (componente que já vem
no Windows 11 e nos Windows 10 atualizados). Não é preciso ser administrador; só o bloqueio de escrita em USB,
opcional, pede essa permissão.

Para conferir uma coleta, arraste a pasta `COLETA_...` sobre o arquivo `Verificar coleta.bat`.

Problemas e sugestões: abra uma *issue* (registro de defeito ou pedido) na aba **Issues** deste repositório e,
se houver erro, anexe o arquivo `%LOCALAPPDATA%\ColetorEvidencias\erros.log`. Use apenas dados de teste, nunca
material de caso real.

## Como rodar a partir do código

Para quem quiser auditar ou executar o código-fonte, com Python 3.12:

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m playwright install chromium
```

Depois, copie a pasta `chrome-win64` do Chromium baixado pelo Playwright
(`%LOCALAPPDATA%\ms-playwright\chromium-*\chrome-win64`) para `componentes\chrome-win64`. O ffmpeg é procurado em
`componentes\ffmpeg\ffmpeg.exe` e, se não estiver lá, no PATH. Para iniciar, dê dois cliques em
`Iniciar Coletor.bat`.

## Observações para o teste

- O DevTools não é bloqueado de antemão, porque a configuração que o desliga desligaria também o controle do
  navegador pela ferramenta: se for aberto, a ferramenta o fecha na hora e registra o fato no relatório. A
  ferramenta não altera o registro do Windows, exceto no bloqueio de escrita em USB, que é opcional e restaurado
  ao final.
- O antivírus pode pedir permissão para a ferramenta "usar o microfone" no primeiro teste de som: é assim que o
  Windows trata a gravação do som que sai pelo fone ou pela caixa.

## Licença

Copyright (C) 2026 Elias Edenis.

Distribuído sob a Licença Pública Geral GNU, versão 3 (GPLv3), cujo texto oficial em inglês está em
[LICENSE](LICENSE). Em linguagem simples: qualquer pessoa pode usar, estudar, copiar e modificar a ferramenta
gratuitamente, mas quem distribuir uma versão modificada precisa publicar o código dela sob a mesma licença. Isso
garante que toda derivação continue aberta e auditável. A ferramenta é fornecida sem garantia.
