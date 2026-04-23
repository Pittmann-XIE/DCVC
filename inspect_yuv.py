#!/usr/bin/env python3
"""Inspect raw YUV420 files and print metadata useful for DCVC configs.

Raw .yuv files do not contain a header, so width and height cannot be read
reliably from the file itself. This script extracts resolution from the file
name when possible, then uses file size to compute frame count. If resolution
is not in the name, it lists common YUV420 resolutions whose frame size divides
the file size exactly.
"""

import argparse
import json
import os
import re
from pathlib import Path


COMMON_RESOLUTIONS = [
    (3840, 2160),
    (2560, 1440),
    (1920, 1080),
    (1600, 900),
    (1280, 720),
    (1024, 768),
    (960, 544),
    (832, 480),
    (720, 576),
    (720, 480),
    (640, 480),
    (416, 240),
    (352, 288),
    (320, 240),
    (176, 144),
]


def yuv420_frame_size(width, height, bit_depth):
    if width % 2 != 0 or height % 2 != 0:
        raise ValueError("YUV420 requires even width and height.")
    bytes_per_sample = 2 if bit_depth > 8 else 1
    return width * height * 3 // 2 * bytes_per_sample


def parse_resolution_from_name(path):
    name = path.name
    patterns = [
        r"(?P<w>\d{3,5})x(?P<h>\d{3,5})",
        r"(?P<w>\d{3,5})X(?P<h>\d{3,5})",
    ]
    for pattern in patterns:
        match = re.search(pattern, name)
        if match:
            return int(match.group("w")), int(match.group("h"))
    return None


def exact_frame_count(file_size, width, height, bit_depth):
    frame_size = yuv420_frame_size(width, height, bit_depth)
    frames, remainder = divmod(file_size, frame_size)
    return frame_size, frames, remainder


def find_candidate_resolutions(file_size, bit_depth):
    candidates = []
    for width, height in COMMON_RESOLUTIONS:
        frame_size, frames, remainder = exact_frame_count(file_size, width, height, bit_depth)
        if frames > 0 and remainder == 0:
            candidates.append({
                "width": width,
                "height": height,
                "frames": frames,
                "frame_size_bytes": frame_size,
            })
    return candidates


def build_dcvc_config(path, width, height, frames):
    return {
        "root_path": str(path.parent.resolve()),
        "test_classes": {
            "MY_VIDEO": {
                "test": 1,
                "base_path": "",
                "src_type": "yuv420",
                "sequences": {
                    path.name: {
                        "width": width,
                        "height": height,
                        "frames": frames,
                        "intra_period": -1,
                    }
                },
            }
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Infer raw YUV420 metadata from filename and file size."
    )
    parser.add_argument("path", type=Path, help="Path to a raw .yuv file")
    parser.add_argument("--width", type=int, help="Known source width")
    parser.add_argument("--height", type=int, help="Known source height")
    parser.add_argument("--bit-depth", type=int, default=8, help="Bit depth, default: 8")
    parser.add_argument(
        "--write-config",
        type=Path,
        help="Optional path to write a one-video DCVC JSON config",
    )
    args = parser.parse_args()

    path = args.path.expanduser()
    if not path.exists():
        raise SystemExit(f"File not found: {path}")
    if not path.is_file():
        raise SystemExit(f"Not a file: {path}")

    file_size = path.stat().st_size
    resolution = None
    source = None

    if args.width is not None or args.height is not None:
        if args.width is None or args.height is None:
            raise SystemExit("Please provide both --width and --height.")
        resolution = (args.width, args.height)
        source = "command line"
    else:
        resolution = parse_resolution_from_name(path)
        if resolution is not None:
            source = "filename"

    print(f"file: {path}")
    print(f"size_bytes: {file_size}")
    print(f"bit_depth: {args.bit_depth}")
    print("format_assumption: yuv420p raw video")

    if resolution is not None:
        width, height = resolution
        frame_size, frames, remainder = exact_frame_count(file_size, width, height, args.bit_depth)
        print(f"width: {width}")
        print(f"height: {height}")
        print(f"resolution_source: {source}")
        print(f"frame_size_bytes: {frame_size}")
        print(f"frames: {frames}")
        print(f"trailing_bytes: {remainder}")
        if remainder != 0:
            print("warning: file size is not an exact multiple of one YUV420 frame.")
        elif args.write_config:
            config = build_dcvc_config(path, width, height, frames)
            args.write_config.write_text(json.dumps(config, indent=4) + "\n", encoding="utf-8")
            print(f"wrote_config: {args.write_config}")
        return

    print("width: unknown")
    print("height: unknown")
    print("note: raw .yuv files do not store resolution metadata.")
    print("candidate_resolutions:")
    candidates = find_candidate_resolutions(file_size, args.bit_depth)
    if not candidates:
        print("  none from the built-in common-resolution list")
        print("  try passing --width and --height if you know them from the dataset/camera.")
        return

    for candidate in candidates:
        print(
            "  "
            f"{candidate['width']}x{candidate['height']}: "
            f"{candidate['frames']} frames "
            f"({candidate['frame_size_bytes']} bytes/frame)"
        )

    print("tip: rerun with --width W --height H --write-config single_yuv_config.json")


if __name__ == "__main__":
    main()
