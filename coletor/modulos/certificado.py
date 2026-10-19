"""Análise do certificado de segurança recebido pelo navegador.

Antivírus e proxies corporativos costumam interceptar conexões seguras:
instalam uma autoridade própria no Windows e apresentam ao navegador um
certificado emitido por ela, no lugar do certificado do site. O navegador
aceita, mas o certificado original deixa de ser visível. A ferramenta detecta
isso conferindo se a autoridade raiz da cadeia está na lista pública de
autoridades reconhecidas (lista da Mozilla, distribuída pelo pacote certifi).
"""

from __future__ import annotations

import base64
from datetime import timezone
from functools import lru_cache

import certifi
from asn1crypto import pem, x509


@lru_cache(maxsize=1)
def _raizes_publicas() -> tuple[set, set]:
    nomes, chaves = set(), set()
    with open(certifi.where(), "rb") as f:
        for _, _, der in pem.unarmor(f.read(), multiple=True):
            cert = x509.Certificate.load(der)
            nomes.add(cert.subject.sha256)
            chaves.add(cert.public_key.sha256)
    return nomes, chaves


def _nome(nome: x509.Name) -> str:
    dados = nome.native
    return dados.get("common_name") or dados.get("organization_name") or nome.human_friendly


def analisar_cadeia(cadeia_base64: list[str]) -> dict:
    certs = [x509.Certificate.load(base64.b64decode(c)) for c in cadeia_base64]
    folha, ultimo = certs[0], certs[-1]
    nomes, chaves = _raizes_publicas()
    if ultimo.self_signed != "no":
        raiz_publica = ultimo.public_key.sha256 in chaves
        raiz = _nome(ultimo.subject)
    else:
        raiz_publica = ultimo.issuer.sha256 in nomes
        raiz = _nome(ultimo.issuer)
    validade = folha["tbs_certificate"]["validity"]
    return {
        "emitido_para": _nome(folha.subject),
        "emitido_por": _nome(folha.issuer),
        "autoridade_raiz": raiz,
        "raiz_publica": raiz_publica,
        "valido_de": int(validade["not_before"].native.astimezone(timezone.utc).timestamp()),
        "valido_ate": int(validade["not_after"].native.astimezone(timezone.utc).timestamp()),
        "cadeia_sha256": [c.sha256.hex() for c in certs],
    }
