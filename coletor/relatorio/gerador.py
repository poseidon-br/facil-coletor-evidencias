"""Gera Relatorio.pdf, Relatorio.html e Declaracao.docx a partir da pasta da coleta.

O PDF é a impressão do mesmo HTML pelo Chromium que acompanha a ferramenta.
Se passar de 10 MB (limite do PJe e do eproc), as miniaturas são reduzidas e,
se ainda assim não couber, o relatório é dividido em volumes.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

from ..nucleo.hashing import sha256_arquivo
from ..nucleo.sessao import LIMITE_JUNTADA
from ..nucleo.tempo import formatar_local
from . import declaracao, modelo, textos

PASTA_MODELOS = Path(__file__).parent
MARGEM_SEGURANCA = int(LIMITE_JUNTADA * 0.95)
QUALIDADES = ((420, 70), (280, 55), (180, 45))  # largura e qualidade JPEG das miniaturas


def _ambiente_jinja() -> Environment:
    env = Environment(loader=FileSystemLoader(PASTA_MODELOS),
                      autoescape=select_autoescape(["html"]), trim_blocks=True, lstrip_blocks=True)
    env.globals["textos"] = textos
    env.globals["local"] = formatar_local
    return env


def _fabrica_miniatura(largura: int, qualidade: int):
    cache = {}

    def miniatura(evidencia: dict) -> str:
        caminho = evidencia["caminho_absoluto"]
        if caminho not in cache:
            with Image.open(caminho) as img:
                img = img.convert("RGB")
                img.thumbnail((largura, largura * 3))
                buffer = io.BytesIO()
                img.save(buffer, "JPEG", quality=qualidade, optimize=True)
            cache[caminho] = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
        return cache[caminho]
    return miniatura


def _embutir_logomarca(pasta: Path, dados: dict) -> None:
    """Embute a logomarca como imagem interna do HTML, mantendo o relatório sem referências externas."""
    pers = dados.get("personalizacao")
    if not (pers and pers.get("logomarca")):
        return
    caminho = pasta / pers["logomarca"]
    if not caminho.is_file():
        return
    tipo = "image/png" if caminho.suffix.lower() == ".png" else "image/jpeg"
    pers["data_uri"] = f"data:{tipo};base64," + base64.b64encode(caminho.read_bytes()).decode()


def _ajustar_certificados(dados: dict) -> None:
    for item in dados["itens"]:
        for n in item["navegacoes"]:
            cert = n.get("certificado")
            if cert and cert.get("valido_ate"):
                cert["valido_ate_legivel"] = datetime.fromtimestamp(cert["valido_ate"]).strftime("%d/%m/%Y")


def _imprimir_pdf(html: Path, destino: Path, identificador: str, navegador) -> None:
    pagina = navegador.new_page()
    try:
        pagina.goto(html.resolve().as_uri(), wait_until="load")
        rodape = ('<div style="font-size:7pt;color:#555;width:100%;padding:0 16mm;display:flex;'
                  'justify-content:space-between;font-family:Segoe UI,Arial">'
                  f'<span>Coleta {identificador}</span>'
                  '<span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>')
        pagina.pdf(path=str(destino), format="A4", print_background=True, display_header_footer=True,
                   header_template="<span></span>", footer_template=rodape,
                   margin={"top": "16mm", "bottom": "18mm", "left": "0mm", "right": "0mm"})
    finally:
        pagina.close()


def gerar(pasta: Path, log=None, executavel_chromium: str | None = None) -> dict:
    """Gera o relatório e a declaração. Registra os hashes no log de fechamento, se fornecido."""
    from playwright.sync_api import sync_playwright

    pasta = Path(pasta)
    dados = modelo.montar(pasta)
    _ajustar_certificados(dados)
    _embutir_logomarca(pasta, dados)
    env = _ambiente_jinja()
    template = env.get_template("modelo.html")
    temporario = pasta / "Verificacao" / "_relatorio_impressao.html"

    def renderizar(destino_html: Path, modo: str, miniatura, itens, sintese=True, anexo=True,
                   parte=None, hashes_pdf=None):
        destino_html.write_text(template.render(
            r=dados, modo=modo, miniatura=miniatura, itens_ficha=itens, incluir_sintese=sintese,
            incluir_anexo=anexo, parte=parte, hashes_pdf=hashes_pdf), encoding="utf-8")

    pdfs: list[Path] = []
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=executavel_chromium, headless=True)
        try:
            for largura, qualidade in QUALIDADES:
                miniatura = _fabrica_miniatura(largura, qualidade)
                destino = pasta / "Relatorio.pdf"
                renderizar(temporario, "pdf", miniatura, dados["itens"])
                _imprimir_pdf(temporario, destino, dados["identificador"], navegador)
                if destino.stat().st_size <= MARGEM_SEGURANCA:
                    pdfs = [destino]
                    break
            else:
                # Não coube: síntese e anexo na parte 1, fichas distribuídas nas partes seguintes.
                (pasta / "Relatorio.pdf").unlink(missing_ok=True)
                pdfs = _dividir(pasta, dados, renderizar, temporario, navegador, miniatura)
        finally:
            navegador.close()
    temporario.unlink(missing_ok=True)

    hashes_pdf = [{"arquivo": p.name, "sha256": sha256_arquivo(p), "tamanho": p.stat().st_size} for p in pdfs]
    miniatura = _fabrica_miniatura(*QUALIDADES[0])
    html = pasta / "Relatorio.html"
    renderizar(html, "html", miniatura, dados["itens"], hashes_pdf=hashes_pdf)
    caminho_declaracao = declaracao.gerar(pasta, dados)

    resultado = {
        "pdf": hashes_pdf,
        "html": {"arquivo": html.name, "sha256": sha256_arquivo(html)},
        "declaracao": {"arquivo": caminho_declaracao.name, "sha256": sha256_arquivo(caminho_declaracao)},
    }
    if log is not None:
        log.registrar("nucleo", "relatorio_gerado", resultado)
        if len(pdfs) > 1:
            log.registrar("nucleo", "ocorrencia", {
                "descricao": f"O relatório passou de 10 MB e foi dividido em {len(pdfs)} volumes.",
                "gravidade": "informacao", "item": None})
    return resultado


def _dividir(pasta, dados, renderizar, temporario, navegador, miniatura) -> list[Path]:
    partes: list[list] = []
    atual: list = []
    for item in dados["itens"]:
        teste = atual + [item]
        renderizar(temporario, "pdf", miniatura, teste, sintese=False, anexo=False)
        provisorio = pasta / "_teste_tamanho.pdf"
        _imprimir_pdf(temporario, provisorio, dados["identificador"], navegador)
        cabe = provisorio.stat().st_size <= MARGEM_SEGURANCA
        provisorio.unlink()
        if cabe or not atual:
            atual = teste
        else:
            partes.append(atual)
            atual = [item]
    if atual:
        partes.append(atual)

    pdfs = []
    destino = pasta / "Relatorio_parte1.pdf"
    renderizar(temporario, "pdf", miniatura, [], sintese=True, anexo=True, parte=1)
    _imprimir_pdf(temporario, destino, dados["identificador"], navegador)
    pdfs.append(destino)
    for numero, itens in enumerate(partes, start=2):
        destino = pasta / f"Relatorio_parte{numero}.pdf"
        renderizar(temporario, "pdf", miniatura, itens, sintese=False, anexo=False, parte=numero)
        _imprimir_pdf(temporario, destino, dados["identificador"], navegador)
        pdfs.append(destino)
    return pdfs
