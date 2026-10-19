"""Monta os dados do relatório a partir do que está gravado na pasta da coleta.

Nada vem da memória do programa: log, manifesto, ambiente e identificação da
ferramenta são lidos do disco. Assim qualquer pessoa pode regenerar o
relatório a partir do pacote e comparar.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from ..nucleo.hashing import sha256_arquivo
from ..nucleo.log import ler_eventos
from ..nucleo.sessao import LIMITE_JUNTADA
from ..nucleo.tempo import formatar_duracao, formatar_hora, formatar_local, ler_iso
from . import textos

LIMITE_RELOGIO_MS = 2000


def tamanho_legivel(n: int | None) -> str:
    if n is None:
        return ""
    for unidade, divisor in (("GB", 1024 ** 3), ("MB", 1024 ** 2), ("KB", 1024)):
        if n >= divisor:
            return f"{n / divisor:.1f} {unidade}".replace(".", ",")
    return "1 byte" if n == 1 else f"{n} bytes"


def _ler_json(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.is_file() else {}


def _origem_download(zone: str | None) -> str | None:
    """Extrai o endereço de origem do Zone.Identifier, quando houver."""
    if not zone:
        return None
    campos = dict(linha.split("=", 1) for linha in zone.splitlines() if "=" in linha)
    return campos.get("HostUrl") or campos.get("ReferrerUrl")


def _linha(situacao: str, texto: str) -> dict:
    return {"situacao": situacao, "texto": texto}


def montar(pasta: Path) -> dict:
    verif = pasta / "Verificacao"
    eventos = ler_eventos(verif / "log.jsonl")
    if (verif / "log_fechamento.jsonl").is_file():
        eventos += ler_eventos(verif / "log_fechamento.jsonl")
    manifesto = _ler_json(verif / "manifesto.json")
    ferramenta = _ler_json(verif / "ferramenta.json")

    por_tipo = defaultdict(list)
    por_item = defaultdict(list)
    for e in eventos:
        por_tipo[e["tipo"]].append(e)
        item = e["dados"].get("item") if isinstance(e["dados"], dict) else None
        if item:
            por_item[item].append(e)

    def primeiro(tipo):
        return por_tipo[tipo][0] if por_tipo[tipo] else None

    abertura = primeiro("sessao_aberta")
    encerramento = primeiro("sessao_encerrada")
    identificador = primeiro("identificador_definido")["dados"]["identificador"]
    inicio, fim = abertura["local"], (encerramento or eventos[-1])["local"]
    duracao = (ler_iso(fim) - ler_iso(inicio)).total_seconds()

    # ------------------------------------------------------------- itens
    itens = []
    for e in por_tipo["item_iniciado"]:
        numero = e["dados"]["item"]
        itens.append(_montar_item(pasta, e, por_item[numero]))

    # ------------------------------------------------------------- quadro
    quadro = []
    verificacao = primeiro("ferramenta_verificada")
    if verificacao and verificacao["dados"].get("oficial"):
        quadro.append(_linha("Conferido", f"Ferramenta oficial e íntegra, versão {verificacao['dados']['versao']}"))
    elif verificacao:
        quadro.append(_linha("Alerta", f"Versão {verificacao['dados']['versao']} de desenvolvimento, sem build "
                                        "oficial assinado para conferência"))

    carimbos = {}
    for e in por_tipo["carimbo"]:
        obtidos = [a for a in e["dados"]["autoridades"] if a.get("obtido")]
        carimbos[e["dados"]["momento"]] = {"evento": e, "obtidos": obtidos,
                                          "falhas": [a for a in e["dados"]["autoridades"] if not a.get("obtido")]}
        nome = "abertura" if e["dados"]["momento"] == "abertura" else "fechamento"
        if obtidos:
            horario = formatar_hora(obtidos[0]["horario_carimbo"])
            autoridades = ", ".join(a["autoridade"] for a in obtidos)
            quadro.append(_linha("Conferido", f"Carimbo do tempo de {nome} às {horario} ({autoridades})"))
        else:
            quadro.append(_linha("Alerta", f"Carimbo do tempo de {nome} não obtido"))

    relogio = primeiro("relogio_conferido")
    diferenca = relogio["dados"]["diferenca_ms"] if relogio else None
    if diferenca is None:
        quadro.append(_linha("Alerta", "Hora oficial não consultada (sem acesso aos servidores de hora)"))
    else:
        texto_dif = f"{abs(diferenca) / 1000:.1f} s".replace(".", ",")
        sentido = "" if abs(diferenca) < 100 else (" (relógio atrasado)" if diferenca > 0 else " (relógio adiantado)")
        situacao = "Conferido" if abs(diferenca) <= LIMITE_RELOGIO_MS else "Alerta"
        quadro.append(_linha(situacao, f"Relógio do computador: diferença de {texto_dif} em relação à hora "
                                        f"oficial{sentido}"))

    amb = primeiro("ambiente_registrado")
    if amb:
        d = amb["dados"]
        problemas = []
        if d["maquina_virtual"]:
            problemas.append("máquina virtual detectada")
        if d["acesso_remoto"]:
            problemas.append("acesso remoto ativo" + (f" ({', '.join(d['programas_acesso_remoto'])})"
                                                      if d["programas_acesso_remoto"] else ""))
        modulos_estranhos = [m for e in por_tipo["modulos_navegador"] for m in e["dados"].get("estranhos", [])]
        if modulos_estranhos:
            problemas.append("bibliotecas de outros programas carregadas no navegador")
        if problemas:
            quadro.append(_linha("Alerta", "Ambiente: " + "; ".join(problemas)))
        else:
            texto = "Ambiente sem máquina virtual e sem acesso remoto ativo"
            if por_tipo["modulos_navegador"]:
                texto += ", sem interferência detectada no navegador"
            quadro.append(_linha("Conferido", texto))

    # Só conta como uso do navegador o item em que ele de fato abriu.
    usou_navegador = bool(por_tipo["protecao_navegador"])
    interceptacao = False
    devtools = por_tipo["devtools_detectado"]
    if usou_navegador:
        if devtools:
            quadro.append(_linha("Alerta", f"Ferramentas de desenvolvedor abertas {len(devtools)} vez(es) e "
                                            "fechadas pela ferramenta (ver Ocorrências)"))
        else:
            quadro.append(_linha("Conferido", "Ferramentas de desenvolvedor do navegador não abertas durante a sessão"))
        navegacoes = [e["dados"] for e in por_tipo["navegacao"]]

        def hosts(lista):
            return sorted({urlsplit(n["endereco_final"]).hostname for n in lista if n.get("endereco_final")})
        sem_certificado = [n for n in navegacoes if not n.get("certificado")]
        interceptadas = [n for n in navegacoes if n.get("certificado") and n["certificado"].get("raiz_publica") is False]
        sem_cadeia = [n for n in navegacoes if n.get("certificado") and n["certificado"].get("raiz_publica") is None]
        if interceptadas:
            interceptacao = True
            raizes = sorted({n["certificado"]["autoridade_raiz"] for n in interceptadas})
            quadro.append(_linha("Alerta", f"Conexão segura intermediada por {', '.join(raizes)}, autoridade instalada "
                                            f"neste computador, em {len(hosts(interceptadas))} site(s): o certificado "
                                            "original do site não pôde ser conferido"))
        if sem_certificado:
            quadro.append(_linha("Alerta", f"{len(hosts(sem_certificado))} site(s) acessado(s) sem conexão segura"))
        if sem_cadeia:
            quadro.append(_linha("Alerta", f"Certificado de {len(hosts(sem_cadeia))} site(s) registrado sem a cadeia "
                                            "completa; a autoridade raiz não foi conferida"))
        if navegacoes and not (interceptadas or sem_certificado or sem_cadeia):
            quadro.append(_linha("Conferido", f"Conexão direta e certificado válido em {len(hosts(navegacoes))} "
                                               "site(s) acessado(s)"))

    itens_usb = [e["dados"] for e in por_tipo["item_iniciado"] if e["dados"].get("coleta_usb")]
    usb_bloqueio = None
    if itens_usb:
        usb_bloqueio = all((d.get("protecao_escrita") or {}).get("ativa") for d in itens_usb)
        if usb_bloqueio:
            quadro.append(_linha("Conferido", "Dispositivo USB coletado com o bloqueio de escrita do Windows "
                                              "ativado antes da conexão"))
        else:
            quadro.append(_linha("Alerta", "Dispositivo USB coletado sem o bloqueio de escrita"))

    token_whatsapp = None
    if por_tipo["token_gerado"]:
        dados_token = por_tipo["token_gerado"][0]["dados"]
        registros = [e for e in por_tipo["identificacao_passo"]
                     if e["dados"].get("rotulo") == "Envio do token de verificação"
                     and not e["dados"].get("pulado")]
        token_whatsapp = {"token": dados_token["token"], "derivacao": dados_token["derivacao"],
                          "registrado": bool(registros)}
        if registros:
            quadro.append(_linha("Conferido", f"Token de verificação {token_whatsapp['token']} enviado no "
                                              "WhatsApp e registrado em print"))
        else:
            quadro.append(_linha("Alerta", f"Token de verificação {token_whatsapp['token']} gerado, mas o "
                                           "envio não foi registrado em print"))

    usou_gravacao = bool(por_tipo["gravacao_iniciada"])
    testes_som = por_tipo["teste_som"]
    if usou_gravacao:
        ok = [t for t in testes_som if t["dados"].get("captado")]
        if ok:
            quadro.append(_linha("Conferido", f"Som captado; teste de som às {formatar_hora(ok[-1]['local'])}"))
        elif testes_som:
            quadro.append(_linha("Alerta", "O teste de som não captou o tom de teste"))
        else:
            quadro.append(_linha("Alerta", "Teste de som não realizado nesta sessão"))

    ocorrencias = [{"hora": formatar_hora(e["local"]), "descricao": e["dados"]["descricao"],
                    "gravidade": e["dados"]["gravidade"], "item": e["dados"].get("item")}
                   for e in por_tipo["ocorrencia"]]

    hash_manifesto = sha256_arquivo(verif / "manifesto.json") if (verif / "manifesto.json").is_file() else None
    tipos_usados = sorted({i["tipo"] for i in itens}, key=list(textos.NOMES_TIPO).index)

    protecao = None
    if usou_navegador:
        protecao = {"deteccoes": [formatar_hora(e["local"]) for e in devtools]}

    return {
        "identificador": identificador,
        "operador": abertura["dados"]["operador"],
        "qualificacao": abertura["dados"].get("qualificacao"),
        "referencia": abertura["dados"].get("referencia"),
        "inicio": formatar_local(inicio),
        "fim": formatar_local(fim),
        "duracao": formatar_duracao(duracao),
        "itens": itens,
        "quadro": quadro,
        "ocorrencias": ocorrencias,
        "hash_manifesto": hash_manifesto,
        "quantidade_arquivos_manifesto": len(manifesto.get("arquivos", [])),
        "atesta": _atesta(tipos_usados, interceptacao, usb_bloqueio),
        "protecao": protecao,
        "token_whatsapp": token_whatsapp,
        "ferramenta": {
            "versao": ferramenta.get("versao"),
            "commit": ferramenta.get("commit"),
            "oficial": ferramenta.get("oficial"),
            "hash_codigo": ferramenta.get("hash_codigo"),
            "python": ferramenta.get("python"),
            "componentes": ferramenta.get("componentes", {}),
        },
        "guia": primeiro("guia_inicial")["dados"] if primeiro("guia_inicial") else None,
        "personalizacao": dict(primeiro("personalizacao")["dados"]) if primeiro("personalizacao") else None,
        "relogio": relogio["dados"] if relogio else None,
        "carimbos": carimbos,
        "ambiente": amb["dados"] if amb else None,
        "modulos_estranhos": sorted({m for e in por_tipo["modulos_navegador"] for m in e["dados"].get("estranhos", [])}),
        "testes_som": [{"hora": formatar_hora(t["local"]), **t["dados"]} for t in testes_som],
        "metodologia": textos.VERSAO_METODOLOGIA,
        "quantidade_eventos": len(eventos),
    }


def _atesta(tipos_usados: list[str], interceptacao: bool, usb_bloqueio: bool | None = None) -> list[tuple]:
    linhas = []
    for tipo in ["geral", *tipos_usados]:
        atesta, nao_atesta = textos.ATESTA[tipo]
        if tipo == "arquivo" and usb_bloqueio:
            atesta += " " + textos.ATESTA_USB
        if tipo == "site" and interceptacao:
            atesta = atesta.replace(", por conexão com certificado válido", "")
            nao_atesta += (" Nesta coleta, a conexão segura foi intermediada por programa instalado no "
                           "computador, o que impede atestar o certificado original do site.")
        linhas.append(("Geral" if tipo == "geral" else textos.NOMES_TIPO[tipo], atesta, nao_atesta))
    return linhas


def _arquivo_info(pasta: Path, dados: dict) -> dict:
    caminho = pasta / dados["arquivo"]
    return {**dados, "nome": caminho.name, "tamanho_legivel": tamanho_legivel(dados.get("tamanho")),
            "acima_limite": (dados.get("tamanho") or 0) > LIMITE_JUNTADA,
            "caminho_absoluto": caminho, "e_imagem": caminho.suffix.lower() in (".png", ".jpg", ".jpeg")}


def _montar_item(pasta: Path, inicio: dict, eventos: list[dict]) -> dict:
    d = inicio["dados"]
    item = {"numero": d["item"], "tipo": d["tipo"], "nome_tipo": textos.NOMES_TIPO.get(d["tipo"], d["tipo"]),
            "descricao": d["descricao"], "dados_inicio": d, "inicio": formatar_hora(inicio["local"])}
    fim = next((e for e in eventos if e["tipo"] == "item_encerrado"), None)
    item["fim"] = formatar_hora(fim["local"]) if fim else None
    item["dados_fim"] = fim["dados"] if fim else {}

    evidencias = []
    for e in eventos:
        if e["tipo"] == "evidencia_registrada":
            info = _arquivo_info(pasta, e["dados"])
            info["hora"] = formatar_hora(e["local"])
            if info.get("inicio"):
                info["intervalo"] = f"{formatar_hora(info['inicio'])} a {formatar_hora(info['fim'])}"
            meta = info.get("metadados_origem")
            if meta:
                info["origem_download"] = _origem_download(meta.get("zone_identifier"))
                info["criacao"] = formatar_local(meta["criacao"], com_fuso=False)
                info["modificacao"] = formatar_local(meta["modificacao"], com_fuso=False)
            evidencias.append(info)
    item["evidencias"] = evidencias
    item["prints"] = [ev for ev in evidencias if ev["papel"] == "print"]
    item["videos"] = [ev for ev in evidencias if ev["papel"] == "video"]
    item["downloads"] = [ev for ev in evidencias if ev["papel"] == "download"]
    item["har"] = next((ev for ev in evidencias if ev["papel"] == "har"), None)
    item["copias"] = [ev for ev in evidencias if ev["papel"] in ("copia", "eml")]
    item["anexos"] = [ev for ev in evidencias if ev["papel"] == "anexo"]
    item["sha256_unico"] = evidencias[0]["sha256"] if len(evidencias) == 1 else None

    def todos(tipo):
        return [{**e["dados"], "hora": formatar_hora(e["local"])} for e in eventos if e["tipo"] == tipo]

    item["navegacoes"] = todos("navegacao")
    item["identificacao"] = todos("identificacao_passo")
    item["token"] = next(iter(todos("token_gerado")), None)
    item["pausas"] = _pausas(eventos)
    item["som"] = todos("som_origem")
    item["trocas_som"] = todos("som_saida_trocada")
    item["gravacao"] = next(iter(todos("gravacao_iniciada")), None)
    gravacao_fim = next(iter(todos("gravacao_encerrada")), None)
    item["tempo_gravado"] = formatar_duracao(gravacao_fim["tempo_gravado_s"]) if gravacao_fim else None
    if item["videos"]:
        item["periodo_gravado"] = (f"{formatar_hora(item['videos'][0]['inicio'])} a "
                                   f"{formatar_hora(item['videos'][-1]['fim'])}")
    item["cabecalhos"] = next(iter(todos("eml_cabecalhos")), None)
    caminho = next(iter(todos("eml_caminho")), None)
    item["saltos"] = caminho["saltos"] if caminho else []
    for salto in item["saltos"]:
        salto["horario_legivel"] = formatar_local(salto["horario"]) if salto.get("horario") else ""
    if item["cabecalhos"] and item["cabecalhos"].get("data_declarada_iso"):
        item["cabecalhos"]["data_legivel"] = formatar_local(item["cabecalhos"]["data_declarada_iso"])
    if item["har"]:
        item["dominios"] = item["har"].get("dominios", [])
        item["requisicoes"] = item["har"].get("requisicoes")
    item["acima_limite"] = [ev for ev in evidencias if ev["acima_limite"] and ev["papel"] in ("copia", "eml", "download")]
    item["quantidade_arquivos"] = len(evidencias)
    return item


def _pausas(eventos: list[dict]) -> list[dict]:
    pausas, aberta = [], None
    for e in eventos:
        if e["tipo"] == "gravacao_pausada":
            aberta = e
        elif e["tipo"] == "gravacao_retomada" and aberta:
            segundos = (ler_iso(e["local"]) - ler_iso(aberta["local"])).total_seconds()
            pausas.append({"inicio": formatar_hora(aberta["local"]), "fim": formatar_hora(e["local"]),
                           "duracao": formatar_duracao(segundos)})
            aberta = None
    return pausas
