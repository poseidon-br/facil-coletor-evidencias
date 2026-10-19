"""Textos fixos do relatório, versão 1 da metodologia (docs/RELATORIO.md, seção 7)."""

VERSAO_METODOLOGIA = "1"

NOMES_TIPO = {
    "arquivo": "Arquivo",
    "eml": "E-mail",
    "site": "Site",
    "whatsapp": "WhatsApp Web",
    "tela": "Gravação da tela",
}

ATESTA = {
    "geral": (
        "que a ferramenta, no computador descrito, registrou o material listado no intervalo de "
        "tempo indicado, e que nenhum arquivo do pacote foi alterado desde o fechamento, desde que "
        "os hashes confiram.",
        "a autoria do conteúdo, a identidade de quem aparece nele, nem a veracidade do que nele se afirma.",
    ),
    "arquivo": (
        "que a cópia é idêntica ao arquivo de origem no momento da coleta.",
        "a origem, a autoria ou o histórico do arquivo antes da coleta. Não recupera arquivos apagados.",
    ),
    "site": (
        "que o servidor identificado entregou o conteúdo registrado, no horário indicado, por conexão "
        "com certificado válido.",
        "quem publicou o conteúdo, nem que ele continue disponível ou inalterado depois da coleta.",
    ),
    "whatsapp": (
        "o que foi exibido e reproduzido na conta conectada durante a gravação, e os números de "
        "telefone mostrados pelo operador.",
        "quem usava os aparelhos, nem o conteúdo não exibido. Mensagens apagadas antes da coleta não "
        "aparecem. O nome exibido é o salvo no aparelho, não um dado do WhatsApp.",
    ),
    "eml": (
        "o conteúdo do arquivo .eml recebido e os dados extraídos dos cabeçalhos dele.",
        "quem redigiu a mensagem, nem que ela não tenha sido alterada antes da coleta. O arquivo "
        "original fica preservado com hash, o que permite exame posterior por perito.",
    ),
    "tela": (
        "o que foi exibido no monitor gravado e o som reproduzido na saída captada, no período indicado.",
        "a origem, a autoria ou a integridade dos arquivos abertos durante a gravação; para isso serve "
        "a coleta de arquivos. O som gravado é regravação do que foi reproduzido, e não o arquivo original.",
    ),
}

# Contextualização da ferramenta e do método na síntese do relatório, em pares
# (título, texto). Escrita em duas camadas: a afirmação técnica e a explicação simples.
METODO_SINTESE = [
    ("O que é esta ferramenta",
     "Este relatório foi gerado pelo Fácil: Coletor de Evidências Digitais Intuitivo, programa "
     "gratuito e de código aberto para a coleta de evidências digitais no Windows. Código aberto significa que o programa "
     "inteiro é público: qualquer perito ou assistente técnico pode ler exatamente o que a ferramenta "
     "faz em cada passo e repetir a conferência. O método, portanto, é auditável."),
    ("Como o relatório é produzido",
     "O relatório é gerado de forma automatizada a partir dos registros feitos durante a coleta. O "
     "operador escolhe o que registrar; como registrar é fixo e automático, sem configuração e sem "
     "edição. Os únicos dados digitados pelo operador são o nome, a qualificação e a referência do "
     "caso, além dos textos que ele mesmo declarar."),
    ("Fundamento do método",
     "O método segue a lógica da cadeia de custódia dos artigos 158-A a 158-F do Código de Processo "
     "Penal, que determinam o registro documentado de cada etapa da prova desde a coleta, e as "
     "diretrizes da norma ABNT NBR ISO/IEC 27037 para a aquisição de evidências digitais: "
     "auditabilidade (o processo pode ser examinado), repetibilidade (qualquer pessoa que recalcule o "
     "hash de um arquivo do pacote obtém o mesmo valor), reprodutibilidade e justificabilidade (cada "
     "mecanismo adotado tem a razão declarada neste relatório). O Superior Tribunal de Justiça, ao "
     "tratar da prova digital, destacou a importância de mecanismos que permitam constatar eventuais "
     "alterações do material coletado, como o hash, aliados a software confiável e auditável (AgRg no "
     "HC 828.054/RN, Quinta Turma, julgado em 23/04/2024)."),
    ("Integridade e tempo",
     "Cada arquivo do pacote recebe um hash SHA-256, a impressão digital matemática usada em "
     "assinaturas digitais e em sistemas como o da rede Bitcoin: qualquer alteração no arquivo, por "
     "menor que seja, muda o resultado. Cada ação da coleta entra num log encadeado, em que cada "
     "registro contém o hash do anterior, de modo que remover ou alterar qualquer linha quebra a "
     "sequência. Na abertura e no fechamento, o hash da coleta é enviado a servidores independentes "
     "de carimbo do tempo (padrão RFC 3161), que atestam que aquele conteúdo existia naquele momento. "
     "O carimbo é uma âncora externa: diferente de registros guardados só no computador, ele é emitido "
     "por terceiro e não pode ser refeito por quem controla a máquina. Só o hash é enviado; nenhum "
     "conteúdo sai do computador."),
    ("Privacidade",
     "A ferramenta funciona sem enviar dados a ninguém. Não há conta, cadastro nem telemetria, e as "
     "evidências não passam por servidor de terceiros, o que a torna adequada também a casos "
     "sigilosos. A única comunicação externa é o envio do hash ao carimbo do tempo, declarado acima."),
    ("Limites do método",
     "O uso desta ferramenta não é exigência legal, e a coleta feita por outros meios não é inválida "
     "por isso. Este relatório declara adiante, módulo a módulo, exatamente o que atesta e o que não "
     "atesta, para que o leitor saiba o alcance e o limite de cada registro."),
    ("Preservação do pacote",
     "Recomenda-se guardar a pasta completa da coleta enquanto a prova interessar. Ela contém os "
     "arquivos originais e os registros técnicos que permitem a qualquer perito refazer a conferência "
     "de integridade descrita na seção Como verificar."),
]

# Bloco do preâmbulo exibido quando a coleta usou o navegador controlado.
METODO_HAR = (
    "Nas coletas feitas pelo navegador, a ferramenta guarda um arquivo no formato HAR (HTTP Archive, "
    "o formato padrão de registro do tráfego entre o navegador e os servidores), com cada requisição e "
    "resposta trocada durante a sessão: endereços, horários, cabeçalhos e o conteúdo entregue pelos "
    "servidores. Em termos práticos, o HAR é a via original do que o servidor enviou, registrada por "
    "baixo da tela: o que aparece nos prints e no vídeo pode ser comparado com o que está no HAR, e "
    "uma alteração feita na página exibida não muda o que o servidor entregou, de modo que a "
    "divergência entre os dois a revela. O arquivo fica na pasta Verificacao, é citado com hash na "
    "ficha do item e pode ser examinado por perito em ferramentas comuns de análise de tráfego. No "
    "WhatsApp Web, o conteúdo das mensagens trafega cifrado de ponta a ponta e o HAR guarda apenas o "
    "conteúdo cifrado; ali, o registro visível vem da gravação contínua e dos prints."
)

ATESTA_USB = (
    "Nas coletas de dispositivo USB com bloqueio de escrita, atesta também que o Windows foi "
    "configurado para recusar gravações em dispositivos USB antes de o dispositivo ser conectado, que "
    "a configuração foi conferida por leitura do registro do sistema e que permaneceu ativa durante a cópia."
)

PROTECAO_SINTESE = (
    "Todo navegador comum traz ferramentas de desenvolvedor (DevTools), acessíveis pelo comando "
    "“inspecionar elemento”, que permitem alterar textos, imagens, nomes e números exibidos numa "
    "página sem que nada mude no servidor de origem. Uma imagem de tela feita depois dessa alteração "
    "não se distingue de uma verdadeira. Por isso, nesta coleta, a ferramenta vigiou durante toda a sessão "
    "qualquer abertura dessas ferramentas, fechando-as de imediato e registrando o fato, e a janela inteira "
    "do navegador, com a barra de endereço, foi gravada em vídeo."
)

PROTECAO_ANEXO = [
    ("Vigilância durante a sessão",
     "A ferramenta controla o navegador por um canal interno, fechado a outros programas, e acompanha "
     "todas as janelas que ele abre. Se o DevTools for aberto, a ferramenta o fecha imediatamente e "
     "registra o fato.",
     "impedir que a página seja alterada por essas ferramentas e deixar registrada qualquer tentativa."),
    ("Gravação da janela inteira",
     "O vídeo mostra a barra de endereço e todo o conteúdo da janela do navegador, incluindo qualquer "
     "painel que tenha sido aberto e qualquer comando digitado na barra de endereço.",
     "permitir que qualquer pessoa confira visualmente o que aconteceu durante a coleta."),
    ("Navegador sem extensões e com perfil novo",
     "Extensões são pequenos programas que podem alterar páginas; o navegador da coleta não tem "
     "nenhuma, e o perfil é criado vazio e apagado ao final.",
     "eliminar alterações vindas de extensões ou de dados de uso anterior."),
    ("Conferência com o tráfego de rede (só para sites)",
     "O registro completo do que o servidor entregou fica guardado (arquivo HAR) e pode ser comparado "
     "com o que aparece nas imagens e no vídeo. No WhatsApp Web essa comparação não é possível, porque "
     "o conteúdo trafega cifrado e só é decifrado dentro da página.",
     "uma alteração feita na tela não altera o que o servidor enviou, então a divergência a revela."),
]

PROTECAO_SEM_BLOQUEIO = (
    "As ferramentas de desenvolvedor não são bloqueadas de antemão porque a configuração que as desliga "
    "desliga também o canal pelo qual a ferramenta controla e registra o navegador. A proteção, por isso, "
    "consiste em detectar e fechar de imediato, com registro."
)

PROTECAO_LIMITE = (
    "Esses cuidados impedem ou revelam alterações feitas pelo navegador. Não impedem a ação de "
    "programas que alterem o navegador por fora, diretamente na memória do computador. Contra isso, a "
    "ferramenta registra o ambiente (programas em execução e bibliotecas de outros programas carregadas "
    "no navegador), cujo resumo consta neste anexo."
)

NOTA_WHATSAPP = ("O nome exibido é o que está salvo no aparelho do usuário; a identificação vale pelo "
                 "número de telefone mostrado.")

TOKEN_SINTESE_TECNICA = (
    "Tecnicamente, o token corresponde aos 12 primeiros caracteres do resumo criptográfico SHA-256 "
    "(hash, a impressão digital matemática) do primeiro registro do log desta coleta, cuja existência "
    "foi fixada pelo carimbo do tempo de abertura da sessão."
)

TOKEN_SINTESE_SIMPLES = (
    "Em termos práticos, isso significa que esse código não existia antes do início desta coleta e não "
    "pode ser recriado para outra. A mensagem com esse código, enviada pelo operador à própria conta e "
    "visível na gravação e no print do roteiro, mostra que a conta de WhatsApp exibida estava conectada "
    "e em uso durante esta sessão, e não em um registro montado antes dela. O vínculo entre a conversa "
    "examinada e o momento da coleta é dado pela gravação contínua da sessão. Qualquer pessoa pode "
    "reconferir o código a partir do primeiro registro do arquivo Verificacao/log.jsonl."
)

TOKEN_NAO_REGISTRADO = (
    "Nesta coleta, o envio do token não foi registrado em print; a amarração temporal apoia-se nos "
    "carimbos do tempo e na gravação contínua da sessão."
)

NOTA_TOKEN = (
    "O token prova que a conta estava conectada e em uso durante esta sessão e que a mensagem com ele "
    "não podia existir antes da abertura da coleta. Não prova a autoria das mensagens; o vínculo da "
    "conversa examinada com o momento da coleta vem da gravação contínua."
)

NOTA_TELA = "Tudo o que apareceu no monitor foi gravado, inclusive notificações de outros programas."

GLOSSARIO = [
    ("Bloqueio de escrita por registro",
     "configuração do Windows que faz o sistema recusar gravações em dispositivos USB conectados "
     "depois de ela ser ativada."),
    ("Captura de retorno (WASAPI loopback)",
     "recurso do Windows que grava o som que está saindo para a caixa ou o fone, sem configuração."),
    ("Carimbo do tempo",
     "registro emitido por servidor independente que prova que um hash já existia em determinado momento."),
    ("Certificado", "documento digital que identifica o servidor de um site e permite a conexão segura."),
    ("DevTools",
     "ferramentas de desenvolvedor do navegador, que permitem alterar a página exibida "
     "(o “inspecionar elemento”)."),
    ("HAR", "formato padrão de registro de todo o tráfego entre o navegador e os servidores."),
    ("Hash (SHA-256)", "impressão digital matemática de um arquivo; qualquer alteração muda o resultado."),
    ("IP", "endereço numérico da máquina que respondeu na internet."),
    ("Log encadeado",
     "registro de ações em que cada linha contém o hash da anterior, de modo que qualquer alteração "
     "quebra a sequência."),
    ("Manifesto", "lista de todos os arquivos do pacote com os respectivos hashes."),
    ("Token de verificação",
     "código derivado do primeiro registro da coleta, enviado pelo operador a si mesmo no WhatsApp "
     "para mostrar que a conta estava em uso durante a sessão."),
    ("UTC", "horário de referência mundial; o horário de Brasília corresponde a UTC-03:00."),
]

COMO_VERIFICAR = [
    "Calcule o SHA-256 de qualquer arquivo do pacote e compare com o valor listado neste relatório "
    "ou no arquivo Verificacao/manifesto.json.",
    "Confira que o hash do manifesto, informado acima, é o mesmo que consta nos carimbos do tempo de "
    "fechamento (pasta Verificacao/carimbos).",
    "As instruções completas estão em Verificacao/LEIA-ME.txt.",
]
