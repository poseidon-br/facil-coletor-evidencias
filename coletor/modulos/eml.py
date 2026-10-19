"""Análise de e-mail salvo em arquivo .eml.

Totalmente offline. Preserva o arquivo original com hash, extrai os
cabeçalhos principais, o caminho entre servidores (cabeçalhos Received) e os
anexos. Não faz verificação DKIM na versão 1.
"""

from __future__ import annotations

import re
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from ..nucleo.hashing import sha256_arquivo
from ..nucleo.sessao import Sessao, nome_seguro
from .arquivo import _copiar_com_hash, _metadados

RE_IP = re.compile(r"\[?((?:\d{1,3}\.){3}\d{1,3}|[0-9a-fA-F:]{3,}:[0-9a-fA-F:]+)\]?")


def _texto(valor) -> str | None:
    return None if valor is None else " ".join(str(valor).split())


def _salto(cabecalho: str) -> dict:
    """Interpreta um cabeçalho Received: de onde, por qual servidor, IP e horário."""
    texto = " ".join(cabecalho.split())
    corpo, _, data = texto.rpartition(";")
    if not corpo:
        corpo, data = texto, ""
    de = re.search(r"\bfrom\s+(\S+)", corpo, re.I)
    por = re.search(r"\bby\s+(\S+)", corpo, re.I)
    trecho_from = corpo[de.start():por.start()] if de and por and por.start() > de.start() else corpo
    ips = [ip for ip in RE_IP.findall(trecho_from) if ip.count(".") == 3 or ip.count(":") >= 2]
    horario = None
    try:
        horario = parsedate_to_datetime(data.strip()).isoformat() if data.strip() else None
    except (TypeError, ValueError):
        pass
    return {"de": de.group(1) if de else None, "por": por.group(1) if por else None,
            "ip": ips[0] if ips else None, "horario": horario, "bruto": texto}


def analisar(caminho: Path) -> dict:
    with open(caminho, "rb") as f:
        mensagem = BytesParser(policy=policy.default).parse(f)
    recebidos = [str(r) for r in mensagem.get_all("Received", [])]
    # Os cabeçalhos Received vêm do mais recente para o mais antigo; o caminho é o inverso.
    caminho_servidores = [_salto(r) for r in reversed(recebidos)]
    data = _texto(mensagem.get("Date"))
    try:
        data_iso = parsedate_to_datetime(data).isoformat() if data else None
    except (TypeError, ValueError):
        data_iso = None
    return {
        "mensagem": mensagem,
        "cabecalhos": {
            "remetente": _texto(mensagem.get("From")),
            "destinatarios": _texto(mensagem.get("To")),
            "copia": _texto(mensagem.get("Cc")),
            "responder_para": _texto(mensagem.get("Reply-To")),
            "caminho_retorno": _texto(mensagem.get("Return-Path")),
            "assunto": _texto(mensagem.get("Subject")),
            "data_declarada": data,
            "data_declarada_iso": data_iso,
            "identificador_mensagem": _texto(mensagem.get("Message-ID")),
        },
        "caminho": caminho_servidores,
    }


def coletar(sessao: Sessao, origem: str | Path):
    origem = Path(origem)
    item = sessao.novo_item("eml", origem.name, {"origem": str(origem)})
    destino = item.pasta_propria / origem.name
    metadados = _metadados(origem)
    hash_origem = _copiar_com_hash(origem, destino)
    hash_copia = sha256_arquivo(destino)
    sessao.registrar_evidencia(item, destino, "eml", {
        "origem": str(origem), "metadados_origem": metadados,
        "sha256_origem": hash_origem, "copia_confere": hash_origem == hash_copia}, sha256=hash_copia)

    analise = analisar(destino)
    sessao.log.registrar("eml", "eml_cabecalhos", {"item": item.numero, **analise["cabecalhos"]})
    sessao.log.registrar("eml", "eml_caminho", {"item": item.numero, "saltos": analise["caminho"]})

    pasta_anexos = item.pasta_propria / "anexos"
    anexos = 0
    for indice, anexo in enumerate(analise["mensagem"].iter_attachments(), start=1):
        nome = anexo.get_filename() or f"anexo-{indice}"
        conteudo = anexo.get_payload(decode=True) or b""
        extensao = Path(nome).suffix
        arquivo = pasta_anexos / f"{indice:02d}_{nome_seguro(Path(nome).stem)}{extensao}"
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)
        sessao.registrar_evidencia(item, arquivo, "anexo", {"nome_original": nome,
                                                             "tipo": anexo.get_content_type()})
        anexos += 1
    sessao.encerrar_item(item, {"anexos": anexos})
    return item
