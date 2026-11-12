# Fácil: Coletor de Provas Digitais Intuitivo

Programa gratuito e de código aberto para coletar provas digitais no Windows, com os registros que a cadeia de
custódia exige. Idealizado por Elias Edenis.

**Versão atual:** 1.0.0, para uso. O pacote é montado nos servidores do GitHub a partir do código público e sai
com atestado de proveniência (prova criptográfica de que o arquivo veio deste repositório). Baixe em
[Releases](https://github.com/poseidon-br/facil-coletor-evidencias/releases).

## Para que serve

O Fácil registra o que está na tela, na rede e nos arquivos de um modo que outra pessoa consegue conferir depois.
O usuário principal é o advogado, não o perito: são três passos (abrir a coleta, escolher o que coletar, encerrar)
e nenhuma decisão técnica. Ao final, a ferramenta entrega um relatório em linguagem simples e uma pasta com as
evidências e os arquivos de verificação.

Exemplos de uso prático:

- **Registro de achados de OSINT** (sigla em inglês para pesquisa em fontes abertas, como sites, redes sociais e
  cadastros públicos): cada página visitada fica registrada com print, vídeo, endereço, horário e a resposta
  original do servidor.
- Conversa no WhatsApp Web, com a identificação da conta e do contato pelo número de telefone.
- Ofensa, ameaça ou anúncio fraudulento publicado em rede social ou site.
- Página de golpe ou de venda falsa, antes que saia do ar.
- E-mail recebido, a partir do arquivo `.eml` (o formato em que os programas de e-mail salvam a mensagem inteira).
- Arquivos de um computador, pendrive ou disco USB, com prova de que a cópia é idêntica ao original.
- O que acontece fora do navegador, como abrir uma pasta ou reproduzir um áudio, pela gravação da tela.

## Origem do projeto

O Fácil foi idealizado por Elias Edenis a partir das necessidades que percebeu no dia a dia, na experiência
prática de investigação e no ensino de investigação de crimes cibernéticos, e dos riscos na coleta de provas
digitais que outras ferramentas de coleta local não cobrem.

O exemplo central é o DevTools (ferramentas de desenvolvedor, abertas pelo comando "inspecionar elemento"), presente
no navegador instalado em qualquer computador. Com ele, qualquer pessoa altera textos, nomes, números e imagens
exibidos numa página sem que nada mude no servidor de origem, e o print feito depois disso não se distingue de um
verdadeiro. Ferramentas que gravam o navegador comum do computador onde a coleta é feita não impedem essa
alteração. O Fácil usa um navegador próprio, em que o DevTools é fechado no mesmo instante em que é aberto e a
tentativa fica registrada no relatório; guarda o arquivo HAR, que é a via original do que o servidor entregou; e
registra automaticamente no relatório todo arquivo baixado durante a coleta.

Antes do lançamento, a ferramenta foi testada por investigadores criminais (policiais civis), peritos e
profissionais da advocacia.

## Cadeia de custódia e proteção tecnológica da prova

Cadeia de custódia é a documentação de tudo o que aconteceu com um vestígio, do momento em que foi encontrado até
o fim do processo, para que se possa confiar que ele é o mesmo e não foi alterado. Na prova digital, isso pede
duas garantias diferentes, e cada recurso do Fácil existe para atender a uma delas:

1. **Que nada foi alterado depois da coleta.** É o papel do hash de cada arquivo, do manifesto, do log encadeado,
   dos carimbos do tempo e do registro no OpenTimestamps: qualquer mudança posterior fica evidente, e a data da
   coleta é atestada por terceiros.
2. **Que nada foi fraudado durante a coleta.** É a proteção tecnológica na produção da prova: o navegador
   próprio e isolado, a vigilância do DevTools, o registro do tráfego em HAR, a gravação contínua e o registro do
   ambiente impedem ou denunciam a manipulação do conteúdo enquanto ele é coletado, como a edição de uma página
   pelas ferramentas de desenvolvedor antes do print.

## Recursos e o porquê de cada um

### Confiança da coleta

- **Carimbo do tempo na abertura e no fechamento.** O hash da coleta é enviado a autoridades independentes de
  carimbo do tempo (padrão RFC 3161), que atestam que aquele conteúdo existia naquele momento. A ferramenta busca
  carimbos de duas autoridades diferentes, para que a falha de uma não deixe a coleta sem testemunha externa. *Resolve:* um
  registro guardado só no computador pode ser refeito por quem controla a máquina; o carimbo é emitido por
  terceiro e delimita no tempo o início e o fim da coleta. Só o hash sai do computador, nunca o conteúdo.
- **Registro no OpenTimestamps (opcional, marcado por padrão).** No fechamento, o hash do manifesto pode ser
  enviado também ao OpenTimestamps, padrão aberto e gratuito que inscreve hashes na blockchain do Bitcoin (o livro
  de registros público dessa rede). O comprovante fica em `Verificacao/manifesto.json.ots`. *Resolve:* dá à coleta
  uma data certa que não depende de nenhuma empresa nem desta ferramenta e que qualquer pessoa confere em
  opentimestamps.org. O relatório explica o que é o registro e como consultá-lo.
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

## Auditabilidade

O Fácil é software de código aberto publicado na internet, e isso é parte do valor da prova que ele produz:

- **Qualquer pessoa lê o que a ferramenta faz.** Perito, assistente técnico ou a parte contrária podem examinar o
  código inteiro, em vez de confiar na palavra do autor ou de uma empresa.
- **Cada relatório aponta a versão exata.** O anexo técnico traz a versão, o commit (identificador da versão exata
  do código no histórico público) e o hash do código em execução. Quem audita sabe exatamente qual código gerou
  aquele relatório, mesmo anos depois.
- **O pacote não passa pelo computador do autor.** O build oficial (o pacote pronto para uso) é montado nos
  servidores do GitHub, a partir do código público, por um roteiro também público
  (`.github/workflows/build.yml`), e recebe um atestado de proveniência que qualquer pessoa confere.
- **A ferramenta confere a si mesma a cada coleta.** Ela recalcula o hash do próprio código e compara com o do
  build oficial; se algum arquivo tiver sido alterado, o relatório informa que foi gerado fora do build oficial.
- **O histórico é permanente.** As versões publicadas e seus hashes não são apagados, para que um relatório de
  hoje continue verificável no futuro.
- **Toda derivação continua aberta.** A licença GPLv3 obriga quem distribuir uma versão modificada a publicar o
  código dela.

## Base legal e normativa

- **Código de Processo Penal, arts. 158-A a 158-F** (incluídos pela Lei 13.964/2019). O art. 158-A define a
  cadeia de custódia como "o conjunto de todos os procedimentos utilizados para manter e documentar a história
  cronológica do vestígio", para rastrear sua posse e manuseio do reconhecimento ao descarte. O art. 158-B lista
  as etapas, entre elas a coleta e o acondicionamento, este com anotação da data, da hora e do nome de quem
  realizou a coleta. O relatório do Fácil documenta essas informações de forma automática.
- **ISO/IEC 27037:2012**, norma internacional com diretrizes para identificação, coleta, aquisição e preservação
  de evidência digital.

A ferramenta apoia o cumprimento dessas regras, mas não decide o valor da prova: isso cabe a quem a avalia no
processo.

## Requisitos

- O programa foi escrito para as versões mais atualizadas do Windows 10 (22H2) e para o Windows 11, de 64 bits.
- Microsoft Edge WebView2 (componente que já vem no Windows 11 e nos Windows 10 atualizados).
- Não é preciso ser administrador; só o bloqueio de escrita em USB, opcional, pede essa permissão.
- Não é preciso instalar Python nem baixar nada além do pacote: ele já traz o navegador, o ffmpeg (programa que
  monta os vídeos) e todas as bibliotecas.

## Como baixar, conferir e instalar

1. Abra [Releases](https://github.com/poseidon-br/facil-coletor-evidencias/releases) e baixe o arquivo
   `Facil-1.0.0.zip` da versão mais recente.
2. Opcional, recomendado para quem vai atestar o uso da ferramenta: confira o pacote baixado (abaixo).
3. Clique com o botão direito no arquivo baixado, escolha **Extrair tudo** e extraia para uma pasta sua, por
   exemplo Documentos. Não execute de dentro do .zip.
4. Na pasta extraída, dê dois cliques em `Iniciar Facil.bat`.
5. O Windows pode mostrar "O Windows protegeu o computador", porque o pacote ainda não tem a assinatura
   Authenticode (o certificado que o Windows reconhece em programas). Clique em **Mais informações** e depois em
   **Executar assim mesmo**. A assinatura do pacote, por enquanto, é o atestado de proveniência.

### Conferir o pacote baixado

Pelo hash, no PowerShell (o resultado deve ser igual ao SHA-256 publicado na página da versão):

```powershell
Get-FileHash .\Facil-1.0.0.zip -Algorithm SHA256
```

Pelo atestado de proveniência, com o [GitHub CLI](https://cli.github.com) (programa de linha de comando do
GitHub). O comando confirma que o arquivo foi montado nos servidores do GitHub, a partir deste repositório:

```powershell
gh attestation verify .\Facil-1.0.0.zip --repo poseidon-br/facil-coletor-evidencias
```

## Como conferir uma coleta

- Arraste a pasta `COLETA_...` sobre o arquivo `Verificar coleta.bat`. Ele confere o log encadeado, o manifesto e
  os carimbos do tempo, e informa qualquer arquivo alterado, ausente ou acrescentado.
- Para o registro no OpenTimestamps, envie o arquivo `Verificacao/manifesto.json.ots` em
  [opentimestamps.org](https://opentimestamps.org). Nas primeiras horas depois da coleta, a consulta informa que o
  registro aguarda confirmação na blockchain.
- O arquivo `Verificacao/LEIA-ME.txt`, dentro de cada coleta, explica a conferência passo a passo.

## Perguntas frequentes

**Substitui a ata notarial?** São meios diferentes. A ata tem a fé pública do tabelião, que declara o que viu. O
Fácil produz um registro técnico que qualquer pessoa pode conferir. A escolha, ou o uso dos dois, cabe ao
profissional responsável pelo caso.

**Precisa de internet?** Para coletar sites e o WhatsApp Web, sim. A análise de e-mail e a coleta de arquivos
funcionam sem internet, mas a coleta fica sem carimbo do tempo, e o relatório registra isso.

**O que sai do meu computador?** Apenas hashes (impressões digitais matemáticas, das quais não se recupera o
conteúdo), enviados às autoridades de carimbo do tempo e, se a opção estiver marcada, ao OpenTimestamps, além da
consulta a servidores públicos de hora. Não há conta, cadastro nem telemetria (envio de dados de uso ao autor).

**Posso usar em caso sigiloso?** Sim. O material coletado fica só na pasta escolhida por você.

**Por que o antivírus reclama?** Antivírus costumam estranhar a gravação de tela e de som e se colocam no meio
das conexões seguras. O guia de uso inicial explica o que fazer, e o relatório registra a escolha.

**A ferramenta prova quem é o autor de uma publicação ou mensagem?** Não. Ela atesta que aquele conteúdo foi
recebido naquele computador, naquele intervalo de tempo. A autoria depende de outros elementos, como dados do
provedor ou perícia.

## Relatos, sugestões e falhas de segurança

Relatos de uso e sugestões de melhoria são bem-vindos, desde que restritos ao objetivo primário do software: a
coleta de provas digitais com os registros da cadeia de custódia.

- Abra uma *issue* (registro de defeito ou pedido) na aba **Issues** deste repositório. Se houver erro, anexe o
  arquivo `dados\erros.log`. Nunca anexe material de caso real: as issues são públicas.
- Falhas de segurança devem ser relatadas de forma reservada, pela aba **Security**, opção **Report a
  vulnerability**.

## Como citar a ferramenta

Em peça ou relatório, indique o nome, a versão e o endereço. A versão e o commit constam do anexo técnico de cada
relatório gerado.

> Fácil: Coletor de Provas Digitais Intuitivo, versão 1.0.0, de Elias Edenis. Disponível em
> https://github.com/poseidon-br/facil-coletor-evidencias.

## Observações de uso

- O DevTools não é bloqueado de antemão, porque a configuração que o desliga desligaria também o controle do
  navegador pela ferramenta: se for aberto, a ferramenta o fecha na hora e registra o fato no relatório. A
  ferramenta não altera o registro do Windows, exceto no bloqueio de escrita em USB, que é opcional e restaurado
  ao final.
- O antivírus pode pedir permissão para a ferramenta "usar o microfone" no primeiro teste de som: é assim que o
  Windows trata a gravação do som que sai pelo fone ou pela caixa.
- A ferramenta é portátil: o registro de erros (`erros.log`) e as preferências ficam na pasta `dados`, dentro da
  pasta da ferramenta, e vão junto quando ela é copiada para outro computador ou para um pen drive. Se essa pasta
  não aceitar gravação, eles vão para `%LOCALAPPDATA%\ColetorEvidencias`.

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
`Iniciar Coletor.bat`. Executada assim, a ferramenta informa no relatório que rodou fora do build oficial.

O pacote publicado é montado por `empacotamento/montar.ps1`, com as versões exatas das bibliotecas listadas em
`empacotamento/requisitos-build.txt`.

## Licença

Copyright (C) 2026 Elias Edenis.

Distribuído sob a Licença Pública Geral GNU, versão 3 (GPLv3), cujo texto oficial em inglês está em
[LICENSE](LICENSE). Em linguagem simples: qualquer pessoa pode usar, estudar, copiar e modificar a ferramenta
gratuitamente, mas quem distribuir uma versão modificada precisa publicar o código dela sob a mesma licença. Isso
garante que toda derivação continue aberta e auditável. A ferramenta é fornecida sem garantia.
