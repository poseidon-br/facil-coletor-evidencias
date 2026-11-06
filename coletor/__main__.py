from . import diagnostico

# Antes da interface, para que o pywebview e as demais bibliotecas já escrevam no erros.log.
diagnostico.iniciar()

from .interface.app import main  # noqa: E402

main()
