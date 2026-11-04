"""Extract only the boot partition from a local ZIP image, never a device."""

import argparse
import json
import struct
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--member", default="ATK-Z20-2.7.0.img")
    parser.add_argument("--output-dir", type=Path, default=Path("build/sd_reference"))
    args = parser.parse_args()
    if not args.archive.is_file():
        parser.error("archive must be a local ZIP file")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.archive) as archive, archive.open(args.member) as stream:
        mbr = stream.read(512)
        if len(mbr) != 512 or mbr[510:] != b"\x55\xaa":
            raise ValueError("Invalid MBR signature")
        entry = mbr[446:462]
        kind = entry[4]
        start, count = struct.unpack_from("<II", entry, 8)
        if kind not in (6, 11, 12, 14) or start < 1 or not 0 < count * 512 < 512 * 1024**2:
            raise ValueError("Unexpected first boot partition")
        if (start + count) * 512 > archive.getinfo(args.member).file_size:
            raise ValueError("Partition exceeds image size")
        remaining = start * 512 - 512
        while remaining:
            block = stream.read(min(remaining, 1024**2))
            if not block:
                raise EOFError("Image ended before boot partition")
            remaining -= len(block)
        remaining = count * 512
        with (args.output_dir / "atk_boot.fat").open("wb") as output:
            while remaining:
                block = stream.read(min(remaining, 1024**2))
                if not block:
                    raise EOFError("Image ended inside boot partition")
                output.write(block)
                remaining -= len(block)
    (args.output_dir / "layout.json").write_text(
        json.dumps(dict(type=kind, start_sector=start, sector_count=count), indent=2),
        encoding="utf-8",
    )
    print("REFERENCE_BOOT_PARTITION_EXTRACTED", start, count * 512)


if __name__ == "__main__":
    main()
