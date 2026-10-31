"""ComfyUI custom node: H3 Director (plan ujec i referencji dla MiniMax H3 Ref2VA).

Instalacja: skopiuj ten katalog do ComfyUI/custom_nodes/ i zrestartuj ComfyUI.
Dokumentacja: README.md oraz INSTALL_AND_TEST.md w tym katalogu.
"""
from .h3_director_node import H3Director

NODE_CLASS_MAPPINGS = {"H3Director": H3Director}
NODE_DISPLAY_NAME_MAPPINGS = {"H3Director": "H3 Director (plan + referencje)"}
WEB_DIRECTORY = "./web"

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
