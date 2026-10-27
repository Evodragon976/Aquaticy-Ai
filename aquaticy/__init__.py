"""aquaticy -- ein KI-Rechercheagent fuer die Kommandozeile."""

import os as _os

_os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

__version__ = "12.6.7"



__codename__ = "Sol"




__stage__ = ""


INTERNAL = bool(__stage__)


VERSION_LABEL = f"{__version__} {__codename__}" + (f" {__stage__}" if __stage__ else "")

__all__ = ["INTERNAL", "VERSION_LABEL", "__codename__", "__stage__", "__version__"]
