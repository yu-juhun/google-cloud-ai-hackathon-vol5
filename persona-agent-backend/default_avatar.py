"""Static fallback avatar used as the Nano Banana evolution base when the
user never uploads a photo (per the v2 design spec's "ベースアバター画像の
扱い" — evolution should still happen off a pre-generated base image, not
skip entirely, when there's no YouCam-personalized photo to start from).
"""
import os

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_CLOSED_PATH = os.path.join(_ASSETS_DIR, "default-avatar-closed.png")
_OPEN_PATH = os.path.join(_ASSETS_DIR, "default-avatar-open.png")

DEFAULT_MIME_TYPE = "image/png"

_closed_bytes: bytes | None = None
_open_bytes: bytes | None = None


def get_default_avatar_closed() -> bytes:
    global _closed_bytes
    if _closed_bytes is None:
        with open(_CLOSED_PATH, "rb") as f:
            _closed_bytes = f.read()
    return _closed_bytes


def get_default_avatar_open() -> bytes:
    global _open_bytes
    if _open_bytes is None:
        with open(_OPEN_PATH, "rb") as f:
            _open_bytes = f.read()
    return _open_bytes
