"""aquaticy -- ein KI-Rechercheagent fuer die Kommandozeile."""

import os as _os

_os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

__version__ = "15.0.0"



__codename__ = ""




__stage__ = ""


INTERNAL = bool(__stage__)


# Seit 15.0.0 darf der Name fehlen: dann heisst die Fassung nur "15.0.0".
VERSION_LABEL = " ".join(t for t in (__version__, __codename__, __stage__) if t)

__all__ = ["INTERNAL", "VERSION_LABEL", "__codename__", "__stage__", "__version__"]
