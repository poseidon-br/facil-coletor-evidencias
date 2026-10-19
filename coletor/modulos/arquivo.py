"""Coleta lógica de arquivos.

Para cada arquivo: lê as datas antes de abri-lo, copia calculando o hash da
origem, calcula o hash da cópia e compara. Falhas são registradas arquivo a
arquivo, sem interromper a coleta. Não recupera arquivos apagados.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ..nucleo.hashing import BLOCO, sha256_arquivo
from ..nucleo.sessao import Item, Sessao

ATRIBUTOS = {
    0x1: "somente leitura", 0x2: "oculto", 0x4: "sistema", 0x20: "arquivo",
    0x100: "temporário", 0x400: "ponto de nova análise", 0x800: "compactado",
    0x1000: "offline", 0x4000: "criptografado", 0x40000: "baixar ao abrir",
    0x400000: "baixar ao acessar dados",
}
ATRIBUTOS_NUVEM = 0x1000 | 0x40000 | 0x400000
SEM_JANELA = 0x08000000


def _iso(segundos: float) -> str:
    return datetime.fromtimestamp(segundos, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _volume(caminho: Path) -> dict:
    raiz = Path(os.path.splitdrive(str(caminho.resolve()))[0] + "\\")
    nome = ctypes.create_unicode_buffer(261)
    sistema = ctypes.create_unicode_buffer(261)
    serie = ctypes.c_uint32()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        str(raiz), nome, 261, ctypes.byref(serie), None, None, sistema, 261)
    dados = {"raiz": str(raiz)}
    if ok:
        dados.update({"rotulo": nome.value, "sistema_arquivos": sistema.value,
                      "numero_serie": f"{serie.value >> 16:04X}-{serie.value & 0xFFFF:04X}"})
    letra = str(raiz)[0]
    if letra.isalpha():
        comando = (f"Get-Partition -DriveLetter {letra} | Get-Disk | "
                   "Select-Object FriendlyName,SerialNumber,BusType | ConvertTo-Json -Compress")
        try:
            saida = subprocess.run(["powershell", "-NoProfile", "-Command", comando],
                                   capture_output=True, text=True, timeout=20,
                                   creationflags=SEM_JANELA).stdout.strip()
            if saida:
                disco = json.loads(saida)
                dados.update({"dispositivo": disco.get("FriendlyName"),
                              "serie_dispositivo": (disco.get("SerialNumber") or "").strip() or None,
                              "barramento": str(disco.get("BusType"))})
        except Exception:
            pass
    return dados


def _zone_identifier(caminho: Path) -> str | None:
    """Informação que o Windows anexa a arquivos baixados, com o endereço de origem."""
    try:
        with open(f"{caminho}:Zone.Identifier", encoding="utf-8", errors="replace") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _metadados(caminho: Path) -> dict:
    st = os.stat(caminho)
    atributos = getattr(st, "st_file_attributes", 0)
    return {
        "tamanho": st.st_size,
        "criacao": _iso(getattr(st, "st_birthtime", st.st_ctime)),
        "modificacao": _iso(st.st_mtime),
        "ultimo_acesso": _iso(st.st_atime),
        "atributos": [nome for bit, nome in ATRIBUTOS.items() if atributos & bit],
        "nuvem_sob_demanda": bool(atributos & ATRIBUTOS_NUVEM),
        "zone_identifier": _zone_identifier(caminho),
    }


def _copiar_com_hash(origem: Path, destino: Path) -> str:
    destino.parent.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha256()
    with open(origem, "rb") as entrada, open(destino, "wb") as saida:
        while bloco := entrada.read(BLOCO):
            h.update(bloco)
            saida.write(bloco)
    return h.hexdigest()


def _coletar_um(sessao: Sessao, item: Item, origem: Path, destino: Path) -> bool:
    try:
        metadados = _metadados(origem)  # antes de abrir o arquivo
        hash_origem = _copiar_com_hash(origem, destino)
        hash_copia = sha256_arquivo(destino)
        os.utime(destino, (os.stat(origem).st_atime, os.stat(origem).st_mtime))
    except OSError as erro:
        motivo = "arquivo em uso ou protegido" if isinstance(erro, PermissionError) else str(erro)
        sessao.log.registrar("arquivo", "arquivo_falhou",
                             {"item": item.numero, "origem": str(origem), "motivo": motivo})
        sessao.ocorrencia(f"Não foi possível copiar {origem}: {motivo}.", "alerta", item.numero, "arquivo")
        return False
    confere = hash_origem == hash_copia
    sessao.registrar_evidencia(item, destino, "copia", {
        "origem": str(origem), "metadados_origem": metadados,
        "sha256_origem": hash_origem, "copia_confere": confere,
    }, sha256=hash_copia)
    if not confere:
        sessao.ocorrencia(f"O hash da cópia de {origem} não confere com o da origem.", "alerta",
                          item.numero, "arquivo")
    if metadados["nuvem_sob_demanda"]:
        sessao.ocorrencia(f"{origem} estava armazenado na nuvem e foi baixado no momento da leitura.",
                          "informacao", item.numero, "arquivo")
    return confere


def coletar(sessao: Sessao, origem: str | Path, progresso=None, contexto_usb: dict | None = None) -> Item:
    """Coleta um arquivo ou uma pasta inteira (recursivamente) como um item.

    contexto_usb: resumo do bloqueio de escrita quando a origem é um dispositivo
    USB coletado pelo fluxo guiado; entra nos dados do item para constar na ficha.
    """
    origem = Path(origem)
    eh_pasta = origem.is_dir()
    volume = _volume(origem)
    dados = {"origem": str(origem), "pasta": eh_pasta, "volume_origem": volume}
    if contexto_usb:
        dados.update({"coleta_usb": True, "protecao_escrita": contexto_usb})
    item = sessao.novo_item("arquivo", origem.name or str(origem), dados)

    volume_destino = _volume(sessao.pasta)
    if (volume.get("numero_serie") and volume.get("numero_serie") == volume_destino.get("numero_serie")
            and not getattr(sessao, "_aviso_mesmo_volume", False)):
        sessao._aviso_mesmo_volume = True
        sessao.ocorrencia("A origem e o destino da cópia estão no mesmo volume (mesma unidade de disco).",
                          "informacao", item.numero, "arquivo")

    if eh_pasta:
        arquivos = sorted(p for p in origem.rglob("*") if p.is_file())
        pares = [(p, item.pasta_propria / origem.name / p.relative_to(origem)) for p in arquivos]
    else:
        pares = [(origem, item.pasta_propria / origem.name)]

    copiados = 0
    for indice, (arquivo, destino) in enumerate(pares, start=1):
        copiados += _coletar_um(sessao, item, arquivo, destino)
        if progresso:
            progresso(indice, len(pares))
    sessao.encerrar_item(item, {"arquivos": len(pares), "copiados": copiados,
                                "falhas": len(pares) - copiados})
    return item
