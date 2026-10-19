"""Manifesto: lista de todos os arquivos do pacote com os respectivos SHA-256.

O hash do manifesto é carimbado no fechamento, o que fixa no tempo o
conteúdo de todo o pacote. Ficam fora dele apenas os arquivos gerados depois
desse carimbo: relatório, declaração, log de fechamento e o próprio carimbo.
"""

from __future__ import annotations

import json
from pathlib import Path

from .. import VERSAO
from .hashing import sha256_arquivo
from .tempo import agora

NOME = "manifesto.json"


def fora_do_manifesto(relativo: str) -> bool:
    nome = relativo.rsplit("/", 1)[-1]
    return (
        relativo.startswith("Relatorio") or relativo == "Declaracao.docx"
        or relativo in ("Verificacao/manifesto.json", "Verificacao/log_fechamento.jsonl")
        or (relativo.startswith("Verificacao/carimbos/") and nome.startswith("fechamento"))
    )


def listar(pasta: Path) -> list[dict]:
    arquivos = []
    for caminho in sorted(p for p in pasta.rglob("*") if p.is_file()):
        relativo = caminho.relative_to(pasta).as_posix()
        if fora_do_manifesto(relativo):
            continue
        arquivos.append({"arquivo": relativo, "tamanho": caminho.stat().st_size,
                         "sha256": sha256_arquivo(caminho)})
    return arquivos


def gerar(pasta: Path, identificador: str, hash_final_log: str) -> Path:
    conteudo = {
        "identificador": identificador,
        "versao_ferramenta": VERSAO,
        "gerado_em": agora()["utc"],
        "algoritmo": "SHA-256",
        "hash_final_log": hash_final_log,
        "arquivos": listar(pasta),
    }
    caminho = pasta / "Verificacao" / NOME
    caminho.write_text(json.dumps(conteudo, ensure_ascii=False, indent=1), encoding="utf-8")
    return caminho


def verificar(pasta: Path) -> list[str]:
    """Confere cada arquivo listado no manifesto. Retorna os problemas encontrados."""
    conteudo = json.loads((pasta / "Verificacao" / NOME).read_text(encoding="utf-8"))
    problemas = []
    listados = set()
    for entrada in conteudo["arquivos"]:
        listados.add(entrada["arquivo"])
        caminho = pasta / entrada["arquivo"]
        if not caminho.is_file():
            problemas.append(f"arquivo ausente: {entrada['arquivo']}")
        elif sha256_arquivo(caminho) != entrada["sha256"]:
            problemas.append(f"arquivo alterado: {entrada['arquivo']}")
    for caminho in pasta.rglob("*"):
        if caminho.is_file():
            relativo = caminho.relative_to(pasta).as_posix()
            if relativo not in listados and not fora_do_manifesto(relativo):
                problemas.append(f"arquivo acrescentado depois do fechamento: {relativo}")
    return problemas


LEIA_ME = """\
COMO VERIFICAR ESTA COLETA

Esta pasta foi gerada pelo Fácil: Coletor de Evidências Digitais Intuitivo,
ferramenta de código aberto. Qualquer pessoa pode conferir que nada foi alterado desde o
fechamento da coleta.

1. Hash de cada arquivo
   O arquivo Verificacao/manifesto.json lista todos os arquivos da pasta com o
   respectivo SHA-256 (impressão digital matemática do arquivo; qualquer
   alteração, por menor que seja, muda o resultado). No Windows, o hash de um
   arquivo pode ser calculado com o comando:
       certutil -hashfile "caminho do arquivo" SHA256

2. Carimbo do tempo
   O hash do manifesto.json foi enviado a autoridades de carimbo do tempo no
   fechamento da coleta. As respostas estão em Verificacao/carimbos, no padrão
   RFC 3161, e podem ser conferidas com OpenSSL:
       openssl ts -reply -in fechamento_<autoridade>.tsr -text
   O campo "Message data" deve ser igual ao SHA-256 do manifesto.json.
   Os carimbos de abertura correspondem ao primeiro evento do log.

3. Log encadeado
   O arquivo Verificacao/log.jsonl registra cada ação da coleta, uma por linha.
   Cada linha contém o hash da anterior; alterar, inserir ou remover qualquer
   linha quebra a cadeia. O arquivo log_fechamento.jsonl continua essa cadeia
   com os eventos posteriores ao manifesto.

4. Verificação automática
   A própria ferramenta confere tudo isso:
       python -m coletor.verificar "caminho desta pasta"

Ficam fora do manifesto, por serem gerados depois do carimbo de fechamento:
o relatório (Relatorio.pdf e Relatorio.html), a declaração editável
(Declaracao.docx), o log de fechamento e os carimbos de fechamento.
"""


def escrever_leia_me(pasta: Path) -> None:
    (pasta / "Verificacao" / "LEIA-ME.txt").write_text(LEIA_ME, encoding="utf-8")
