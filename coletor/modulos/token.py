"""Token de verificação do WhatsApp Web.

O token é derivado do hash do evento 0 do log (sessao_aberta), que é
exatamente o valor fixado pelo carimbo do tempo de abertura. Por isso ele não
podia existir antes do início da coleta e qualquer perito pode reconferir a
derivação a partir da primeira linha de Verificacao/log.jsonl.
"""

from __future__ import annotations

TAMANHO = 12
GRUPO = 4
DERIVACAO = ("12 primeiros caracteres hexadecimais do hash do evento 0 do log, "
             "em maiúsculas, em grupos de 4")


def derivar(hash_evento0: str) -> str:
    """86e4c0b83a5f... vira 86E4-C0B8-3A5F."""
    if not hash_evento0 or len(hash_evento0) < TAMANHO:
        raise ValueError("hash do evento 0 ausente ou curto demais para derivar o token")
    base = hash_evento0[:TAMANHO].upper()
    return "-".join(base[i:i + GRUPO] for i in range(0, TAMANHO, GRUPO))
