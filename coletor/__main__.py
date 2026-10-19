import os
import sys
from pathlib import Path

# Sem console (pythonw), os erros iriam para lugar nenhum; na fase de testes vão para um arquivo.
if sys.stderr is None:
    pasta = Path(os.environ.get("LOCALAPPDATA", ".")) / "ColetorEvidencias"
    pasta.mkdir(parents=True, exist_ok=True)
    sys.stderr = sys.stdout = open(pasta / "erros.log", "a", encoding="utf-8", buffering=1)

from .interface.app import main  # noqa: E402

main()
