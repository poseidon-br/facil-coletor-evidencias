"""Registro do hash do manifesto no OpenTimestamps.

O OpenTimestamps é um padrão aberto de carimbo do tempo que usa a blockchain
do Bitcoin como testemunha. Servidores públicos de calendário recebem hashes,
reúnem todos num único resumo e o gravam numa transação do Bitcoin. Só o hash
é enviado, e ainda combinado com um número aleatório, de modo que nem o hash
do manifesto chega ao calendário.

O comprovante (arquivo .ots) sai daqui como pendente: traz o compromisso do
calendário, e a inscrição na blockchain é concluída nas horas seguintes. O
formato segue o do cliente oficial (python-opentimestamps), para que o
arquivo seja aceito em opentimestamps.org e pelo comando "ots".
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

# Servidores de envio padrão do cliente oficial (lista DEFAULT_AGGREGATORS).
CALENDARIOS = (
    "https://a.pool.opentimestamps.org",
    "https://b.pool.opentimestamps.org",
    "https://a.pool.eternitywall.com",
    "https://ots.btc.catallaxy.com",
)
QUANTIDADE_DESEJADA = 2
RESPOSTA_MAXIMA = 10000  # bytes, o mesmo limite do cliente oficial
SITE_CONSULTA = "https://opentimestamps.org"

MAGICA = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"
VERSAO_FORMATO = 1
OP_SHA256 = 0x08
OP_ACRESCENTAR = 0xF0
OPS_SIMPLES = frozenset({0x02, 0x03, 0x08, 0x67, 0xF2, 0xF3})  # sha1, ripemd160, sha256, keccak256, inverter, hex
OPS_COM_ARGUMENTO = frozenset({0xF0, 0xF1})  # acrescentar ao fim, acrescentar ao início
ATESTADO_PENDENTE = bytes.fromhex("83dfe30d2ef90c8e")
ATESTADO_BITCOIN = bytes.fromhex("0588960d73d71901")
PROFUNDIDADE_MAXIMA = 256


class _Leitor:
    def __init__(self, dados: bytes):
        self.dados = dados
        self.pos = 0

    def bytes(self, quantidade: int) -> bytes:
        if self.pos + quantidade > len(self.dados):
            raise ValueError("comprovante truncado")
        trecho = self.dados[self.pos:self.pos + quantidade]
        self.pos += quantidade
        return trecho

    def byte(self) -> int:
        return self.bytes(1)[0]

    def varuint(self) -> int:
        valor = deslocamento = 0
        while True:
            b = self.byte()
            valor |= (b & 0x7F) << deslocamento
            if not b & 0x80:
                return valor
            deslocamento += 7
            if deslocamento > 63:
                raise ValueError("número inválido no comprovante")

    def varbytes(self, maximo: int) -> bytes:
        tamanho = self.varuint()
        if tamanho > maximo:
            raise ValueError("campo maior que o permitido no comprovante")
        return self.bytes(tamanho)

    @property
    def terminou(self) -> bool:
        return self.pos == len(self.dados)


def _varuint(valor: int) -> bytes:
    saida = bytearray()
    while True:
        b = valor & 0x7F
        valor >>= 7
        if valor:
            saida.append(b | 0x80)
        else:
            saida.append(b)
            return bytes(saida)


def _varbytes(dados: bytes) -> bytes:
    return _varuint(len(dados)) + dados


def _ler_no(leitor: _Leitor, nivel: int = 0) -> dict:
    """Lê um nó da árvore do comprovante: atestados e operações, cada operação com o nó seguinte."""
    if nivel > PROFUNDIDADE_MAXIMA:
        raise ValueError("comprovante com encadeamento longo demais")
    no = {"atestados": [], "ops": []}

    def ler_item(marca: int) -> None:
        if marca == 0x00:
            tipo = leitor.bytes(8)
            no["atestados"].append((tipo, leitor.varbytes(8192)))
        elif marca in OPS_COM_ARGUMENTO:
            argumento = leitor.varbytes(4096)
            no["ops"].append((marca, argumento, _ler_no(leitor, nivel + 1)))
        elif marca in OPS_SIMPLES:
            no["ops"].append((marca, b"", _ler_no(leitor, nivel + 1)))
        else:
            raise ValueError(f"operação desconhecida no comprovante (0x{marca:02x})")

    marca = leitor.byte()
    while marca == 0xFF:  # 0xFF anuncia que há outro item depois deste
        ler_item(leitor.byte())
        marca = leitor.byte()
    ler_item(marca)
    return no


def _escrever_no(no: dict) -> bytes:
    itens = [b"\x00" + tipo + _varbytes(carga) for tipo, carga in no["atestados"]]
    for marca, argumento, seguinte in no["ops"]:
        itens.append(bytes([marca]) + (_varbytes(argumento) if marca in OPS_COM_ARGUMENTO else b"")
                     + _escrever_no(seguinte))
    if not itens:
        raise ValueError("comprovante sem atestado")
    return b"".join(b"\xff" + item for item in itens[:-1]) + itens[-1]


def _atestados(no: dict) -> tuple[list[str], list[int]]:
    """Percorre a árvore e devolve os calendários com registro pendente e os blocos do Bitcoin atestados."""
    pendentes, blocos = [], []
    for tipo, carga in no["atestados"]:
        if tipo == ATESTADO_PENDENTE:
            pendentes.append(_Leitor(carga).varbytes(1000).decode("ascii", "replace"))
        elif tipo == ATESTADO_BITCOIN:
            blocos.append(_Leitor(carga).varuint())
    for _, _, seguinte in no["ops"]:
        p, b = _atestados(seguinte)
        pendentes += p
        blocos += b
    return pendentes, blocos


def ler_arquivo(bruto: bytes) -> dict:
    """Lê um arquivo .ots; lança ValueError se não for um comprovante bem formado."""
    leitor = _Leitor(bruto)
    if leitor.bytes(len(MAGICA)) != MAGICA:
        raise ValueError("não é um arquivo do OpenTimestamps")
    if leitor.varuint() != VERSAO_FORMATO:
        raise ValueError("versão do formato não reconhecida")
    if leitor.byte() != OP_SHA256:
        raise ValueError("o comprovante não usa SHA-256")
    resumo = leitor.bytes(32)
    pendentes, blocos = _atestados(_ler_no(leitor))
    if not leitor.terminou:
        raise ValueError("sobram dados depois do comprovante")
    if not (pendentes or blocos):
        raise ValueError("comprovante sem atestado")
    return {"resumo": resumo, "pendentes": pendentes, "blocos_bitcoin": blocos}


def _enviar(url: str, resumo: bytes, tempo_limite: float) -> bytes:
    pedido = urllib.request.Request(
        url.rstrip("/") + "/digest", data=resumo,
        headers={"Accept": "application/vnd.opentimestamps.v1", "User-Agent": "Facil-Coletor"})
    with urllib.request.urlopen(pedido, timeout=tempo_limite) as resposta:
        bruto = resposta.read(RESPOSTA_MAXIMA + 1)
    if len(bruto) > RESPOSTA_MAXIMA:
        raise ValueError("resposta do calendário maior que o permitido")
    return bruto


def registrar(dados: bytes, destino: Path, tempo_limite: float = 8.0) -> dict:
    """Envia o SHA-256 de `dados` aos calendários e grava o comprovante pendente em `destino`.

    Retorna um registro por calendário consultado, com sucesso ou motivo da falha.
    Nenhum arquivo é gravado se nenhum calendário responder.
    """
    resumo = hashlib.sha256(dados).digest()
    # O número aleatório impede que o calendário conheça o hash do manifesto; ele fica no comprovante.
    aleatorio = secrets.token_bytes(16)
    enviado = hashlib.sha256(resumo + aleatorio).digest()

    registros, respostas = [], []
    for url in CALENDARIOS:
        if len(respostas) >= QUANTIDADE_DESEJADA:
            break
        registro = {"servidor": url}
        try:
            bruto = _enviar(url, enviado, tempo_limite)
            leitor = _Leitor(bruto)
            no = _ler_no(leitor)
            if not leitor.terminou:
                raise ValueError("resposta do calendário com dados a mais")
            pendentes, blocos = _atestados(no)
            if not (pendentes or blocos):
                raise ValueError("resposta do calendário sem atestado")
            respostas.append(no)
            registro.update({"obtido": True, "calendarios": pendentes})
        except Exception as erro:
            log.warning("OpenTimestamps: sem registro em %s: %r", url, erro)
            registro.update({"obtido": False, "motivo": str(erro) or type(erro).__name__})
        registros.append(registro)

    resultado = {"hash_registrado": resumo.hex(), "servidores": registros, "obtidos": len(respostas),
                 "arquivo": None, "sha256_arquivo": None}
    if respostas:
        reunido = {"atestados": [a for no in respostas for a in no["atestados"]],
                   "ops": [o for no in respostas for o in no["ops"]]}
        arvore = {"atestados": [], "ops": [
            (OP_ACRESCENTAR, aleatorio, {"atestados": [], "ops": [(OP_SHA256, b"", reunido)]})]}
        conteudo = (MAGICA + _varuint(VERSAO_FORMATO) + bytes([OP_SHA256]) + resumo
                    + _escrever_no(arvore))
        if ler_arquivo(conteudo)["resumo"] != resumo:  # relê o que montou antes de gravar
            raise ValueError("comprovante montado não corresponde ao hash")
        destino.write_bytes(conteudo)
        resultado.update({"arquivo": destino.name, "sha256_arquivo": hashlib.sha256(conteudo).hexdigest()})
    return resultado
