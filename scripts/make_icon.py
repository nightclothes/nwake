"""Write the same icon used by the running app into the Windows executable."""

import argparse
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice

from nwake.theme import brand_image


def write_icon(path: Path) -> None:
    sizes = (16, 24, 32, 48, 64, 128, 256)
    offset = 6 + 16 * len(sizes)
    entries = bytearray(struct.pack("<HHH", 0, 1, len(sizes)))
    frames = bytearray()
    for size in sizes:
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not brand_image(size).save(buffer, "PNG"):
            raise RuntimeError("Could not encode the app icon")
        png = bytes(buffer.data())
        entries.extend(
            struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(png), offset)
        )
        frames.extend(png)
        offset += len(png)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(entries + frames)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    write_icon(parser.parse_args().path)
