"""Carimbo do tempo (RFC 3161).

Só o hash é enviado; o conteúdo nunca sai do computador. A ferramenta tenta
obter dois carimbos de autoridades diferentes, para que a falta de uma não
deixe a coleta sem testemunha externa.
"""

from __future__ import annotations

import hashlib
import secrets
import urllib.request
from pathlib import Path

from asn1crypto import tsp

AUTORIDADES = (
    ("FreeTSA", "https://freetsa.org/tsr"),
    ("SSL.com", "http://ts.ssl.com"),
    ("QuoVadis", "http://ts.quovadisglobal.com/eu"),
    ("DigiCert", "http://timestamp.digicert.com"),
    ("GlobalSign", "http://timestamp.globalsign.com/tsa/r6advanced1"),
    ("Sectigo", "http://timestamp.sectigo.com"),
)
QUANTIDADE_DESEJADA = 2
STATUS_ACEITOS = ("granted", "granted_with_mods")


def _pedir(url: str, requisicao: bytes, tempo_limite: float) -> bytes:
    pedido = urllib.request.Request(
        url, data=requisicao, headers={"Content-Type": "application/timestamp-query"})
    with urllib.request.urlopen(pedido, timeout=tempo_limite) as resposta:
        return resposta.read()


def montar_pedido(resumo: bytes) -> tuple[bytes, int]:
    nonce = secrets.randbits(63)
    pedido = tsp.TimeStampReq({
        "version": "v1",
        "message_imprint": {"hash_algorithm": {"algorithm": "sha256"}, "hashed_message": resumo},
        "nonce": nonce,
        "cert_req": True,
    })
    return pedido.dump(), nonce


def ler_resposta(bruto: bytes) -> dict:
    """Extrai os dados do carimbo; lança ValueError se a resposta não for um carimbo válido."""
    resposta = tsp.TimeStampResp.load(bruto)
    status = resposta["status"]["status"].native
    if status not in STATUS_ACEITOS:
        raise ValueError(f"pedido recusado pela autoridade ({status})")
    token = resposta["time_stamp_token"]
    info = token["content"]["encap_content_info"]["content"].parsed
    return {
        "resumo": info["message_imprint"]["hashed_message"].native,
        "algoritmo": info["message_imprint"]["hash_algorithm"]["algorithm"].native,
        "nonce": info["nonce"].native,
        "horario": info["gen_time"].native,
        "numero_serie": info["serial_number"].native,
        "politica": info["policy"].dotted,
    }


def carimbar(dados: bytes, pasta: Path, prefixo: str, tempo_limite: float = 10.0) -> list[dict]:
    """Carimba o SHA-256 de `dados` e grava cada resposta em `pasta`.

    Retorna um registro por autoridade consultada, com sucesso ou motivo da falha.
    """
    pasta.mkdir(parents=True, exist_ok=True)
    resumo = hashlib.sha256(dados).digest()
    registros = []
    obtidos = 0
    for nome, url in AUTORIDADES:
        if obtidos >= QUANTIDADE_DESEJADA:
            break
        registro = {"autoridade": nome, "url": url, "hash_carimbado": resumo.hex()}
        try:
            pedido, nonce = montar_pedido(resumo)
            bruto = _pedir(url, pedido, tempo_limite)
            info = ler_resposta(bruto)
            if info["algoritmo"] != "sha256" or info["resumo"] != resumo:
                raise ValueError("o carimbo devolvido não corresponde ao hash enviado")
            if info["nonce"] != nonce:
                raise ValueError("o carimbo devolvido não corresponde ao pedido")
            arquivo = pasta / f"{prefixo}_{nome.lower().replace('.', '')}.tsr"
            arquivo.write_bytes(bruto)
            registro.update({
                "obtido": True,
                "arquivo": arquivo.name,
                "horario_carimbo": info["horario"].isoformat().replace("+00:00", "Z"),
                "numero_serie": str(info["numero_serie"]),
                "politica": info["politica"],
            })
            obtidos += 1
        except Exception as erro:
            registro.update({"obtido": False, "motivo": str(erro) or type(erro).__name__})
        registros.append(registro)
    return registros
