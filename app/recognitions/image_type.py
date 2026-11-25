"""파일 앞부분 바이트(시그니처)로 실제 이미지 형식을 판별한다.

클라이언트가 보내는 Content-Type은 바꿔서 보낼 수 있으므로 믿지 않는다.
"""

# HEIC/HEIF 파일의 ftyp 박스에 들어가는 브랜드 값
_HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}


def detect_image_type(data: bytes) -> str | None:
    """jpeg / png / webp / heic 중 하나를 돌려주고, 해당하지 않으면 None."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if len(data) >= 12 and data[4:8] == b"ftyp" and data[8:12] in _HEIF_BRANDS:
        return "heic"
    return None
