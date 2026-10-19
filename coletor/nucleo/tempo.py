"""Horários da coleta.

O relógio do computador nunca é corrigido. Cada registro guarda o horário
UTC, o horário local com fuso e um contador monotônico (que nunca volta
atrás), e a diferença em relação à hora oficial é medida e registrada.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

SERVIDORES_NTP = ("a.st1.ntp.br", "b.st1.ntp.br", "c.st1.ntp.br")


def agora() -> dict:
    """Retorna o instante atual nas três formas registradas no log.

    O contador monotônico vai em microssegundos para caber com folga no limite
    de inteiros exatos do JSON canônico (2^53).
    """
    utc = datetime.now(timezone.utc)
    local = utc.astimezone()
    return {
        "utc": utc.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "local": local.isoformat(timespec="milliseconds"),
        "monotonico": time.monotonic_ns() // 1000,
    }


def ler_iso(texto: str) -> datetime:
    return datetime.fromisoformat(texto.replace("Z", "+00:00"))


def fuso(dt: datetime) -> str:
    """Fuso no formato UTC-03:00."""
    deslocamento = dt.utcoffset()
    total = int(deslocamento.total_seconds()) if deslocamento else 0
    sinal = "-" if total < 0 else "+"
    total = abs(total)
    return f"UTC{sinal}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def formatar_local(texto_iso: str, com_fuso: bool = True) -> str:
    """14/10/2026 15:32:07 (UTC-03:00)"""
    dt = ler_iso(texto_iso).astimezone()
    base = dt.strftime("%d/%m/%Y %H:%M:%S")
    return f"{base} ({fuso(dt)})" if com_fuso else base


def formatar_hora(texto_iso: str) -> str:
    """15:32:07"""
    return ler_iso(texto_iso).astimezone().strftime("%H:%M:%S")


def formatar_duracao(segundos: float) -> str:
    """26 min 34 s"""
    segundos = int(round(segundos))
    horas, resto = divmod(segundos, 3600)
    minutos, seg = divmod(resto, 60)
    partes = []
    if horas:
        partes.append(f"{horas} h")
    if minutos or horas:
        partes.append(f"{minutos} min")
    partes.append(f"{seg} s")
    return " ".join(partes)


def consultar_ntp(servidores=SERVIDORES_NTP, tempo_limite: float = 3.0) -> list[dict]:
    """Mede a diferença do relógio local em relação a servidores de hora.

    Diferença positiva significa relógio local atrasado.
    """
    import ntplib

    cliente = ntplib.NTPClient()
    resultados = []
    for servidor in servidores:
        try:
            resposta = cliente.request(servidor, version=3, timeout=tempo_limite)
            resultados.append({
                "servidor": servidor,
                "diferenca_ms": int(round(resposta.offset * 1000)),
                "atraso_rede_ms": int(round(resposta.delay * 1000)),
            })
        except Exception as erro:  # rede indisponível, servidor fora do ar
            resultados.append({"servidor": servidor, "erro": str(erro) or type(erro).__name__})
    return resultados


def diferenca_mediana_ms(resultados: list[dict]) -> int | None:
    valores = sorted(r["diferenca_ms"] for r in resultados if "diferenca_ms" in r)
    if not valores:
        return None
    return valores[len(valores) // 2]
