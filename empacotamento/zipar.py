"""Compacta o conteúdo da pasta do pacote num .zip, sem pasta-raiz.

O "Extrair tudo" do Windows já cria uma pasta com o nome do .zip; uma pasta-raiz
dentro dele repetiria o nome e alongaria os caminhos.

Uso: python -I zipar.py <pasta> <arquivo.zip>
"""

import sys
import zipfile
from pathlib import Path

pasta, destino = Path(sys.argv[1]), Path(sys.argv[2])
destino.unlink(missing_ok=True)
arquivos = sorted(p for p in pasta.rglob("*") if p.is_file())
with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for i, arquivo in enumerate(arquivos, 1):
        z.write(arquivo, arquivo.relative_to(pasta))
        if i % 1000 == 0:
            print(f"{i} de {len(arquivos)} arquivos", flush=True)
print(f"{len(arquivos)} arquivos compactados")
