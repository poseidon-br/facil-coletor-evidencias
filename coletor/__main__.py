import sys

from . import diagnostico

# Antes da interface, para que o pywebview e as demais bibliotecas já escrevam no erros.log.
diagnostico.iniciar()
diagnostico.preparar_janela()

try:
    from .interface.app import main
    main()
except Exception:
    diagnostico.log.critical("A janela não abriu ou fechou por erro", exc_info=True)
    diagnostico.avisar_falha_abertura()
    sys.exit(1)
