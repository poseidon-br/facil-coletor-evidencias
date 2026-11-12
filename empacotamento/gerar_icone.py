"""Gera coletor/recursos/facil.ico a partir dos desenhos em SVG.

Cada tamanho usa o desenho feito para ele: 16 e 20 px o de 16, 24 px o de 24 e,
a partir de 32 px, o desenho completo. A renderização é a do Chromium do projeto,
com fundo transparente. Também gera uma folha de conferência ampliada.

Uso, na raiz do projeto: .venv/Scripts/python -I empacotamento/gerar_icone.py [pasta da folha]
"""

import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

RAIZ = Path(__file__).resolve().parents[1]
RECURSOS = RAIZ / "coletor" / "recursos"
CHROMIUM = RAIZ / "componentes" / "chrome-win64" / "chrome.exe"
TAMANHOS = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]


def desenho(tamanho: int) -> Path:
    if tamanho <= 20:
        return RECURSOS / "facil-16.svg"
    if tamanho <= 24:
        return RECURSOS / "facil-24.svg"
    return RECURSOS / "facil.svg"


def renderizar(pagina, svg: Path, tamanho: int) -> Image.Image:
    codigo = svg.read_text(encoding="utf-8")
    pagina.set_content(
        f'<html><body style="margin:0;background:transparent">'
        f'<div id="i" style="width:{tamanho}px;height:{tamanho}px">'
        f'{codigo.replace("<svg ", f"<svg style=\"display:block;width:{tamanho}px;height:{tamanho}px\" ", 1)}'
        f"</div></body></html>")
    png = pagina.locator("#i").screenshot(omit_background=True)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def folha(imagens: dict[int, Image.Image], destino: Path) -> None:
    escala, margem = 4, 16
    largura = sum(t * escala for t in TAMANHOS if t <= 64) + margem * 8
    altura = 64 * escala + margem * 2
    final = Image.new("RGBA", (largura, altura * 2), "#ffffff")
    for linha, fundo in enumerate(("#f3f3f3", "#202020")):
        faixa = Image.new("RGBA", (largura, altura), fundo)
        x = margem
        for t in (t for t in TAMANHOS if t <= 64):
            ampliada = imagens[t].resize((t * escala, t * escala), Image.NEAREST)
            faixa.alpha_composite(ampliada, (x, margem + (64 - t) * escala // 2))
            x += t * escala + margem
        final.paste(faixa, (0, linha * altura))
    final.save(destino)
    imagens[256].save(destino.with_name("icone-256.png"))


def main() -> None:
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=str(CHROMIUM))
        pagina = navegador.new_page(device_scale_factor=1)
        imagens = {t: renderizar(pagina, desenho(t), t) for t in TAMANHOS}
        navegador.close()
    for t, imagem in imagens.items():
        if imagem.size != (t, t):
            raise SystemExit(f"tamanho {t}: renderizado com {imagem.size}")
    ico = RECURSOS / "facil.ico"
    imagens[256].save(ico, format="ICO", sizes=[(t, t) for t in TAMANHOS],
                      append_images=[imagens[t] for t in TAMANHOS if t != 256])
    print(f"{ico.relative_to(RAIZ)}: {ico.stat().st_size} bytes")
    if len(sys.argv) > 1:
        folha(imagens, Path(sys.argv[1]) / "icone-folha.png")


if __name__ == "__main__":
    main()
