#!/usr/bin/env python3
"""Crop a raw 8-bit 4:2:0 YUV video frame by frame.

The default layout is planar yuv420p/I420: Y plane, then U plane, then V plane.
Use --layout nv12 if your file stores chroma as interleaved UV rows.
"""

import argparse
from pathlib import Path


def even(value):
    return value - (value % 2)


def parse_args():
    parser = argparse.ArgumentParser(description="Crop raw 8-bit 4:2:0 YUV video.")
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path("/home/fe/xie/S10_R_00_00.yuv"),
        help="Input .yuv file",
    )
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        default=Path("/home/fe/xie/S10_R_00_00_1920x1200.yuv"),
        help="Output cropped .yuv file",
    )
    parser.add_argument("--src-width", type=int, default=3840)
    parser.add_argument("--src-height", type=int, default=2160)
    parser.add_argument("--crop-width", type=int, default=1920)
    parser.add_argument("--crop-height", type=int, default=1200)
    parser.add_argument(
        "--x",
        type=int,
        default=None,
        help="Left crop offset. Default: center crop.",
    )
    parser.add_argument(
        "--y",
        type=int,
        default=None,
        help="Top crop offset. Default: center crop.",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=-1,
        help="Number of frames to crop. Default: all frames.",
    )
    parser.add_argument(
        "--layout",
        choices=("yuv420p", "nv12"),
        default="yuv420p",
        help="Input/output chroma layout. Default: yuv420p.",
    )
    return parser.parse_args()


def validate_args(args):
    if args.src_width % 2 or args.src_height % 2:
        raise SystemExit("YUV420 requires even source width and height.")
    if args.crop_width % 2 or args.crop_height % 2:
        raise SystemExit("YUV420 requires even crop width and height.")
    if args.crop_width > args.src_width or args.crop_height > args.src_height:
        raise SystemExit("Crop size must fit inside source size.")

    x = even((args.src_width - args.crop_width) // 2) if args.x is None else args.x
    y = even((args.src_height - args.crop_height) // 2) if args.y is None else args.y
    if x % 2 or y % 2:
        raise SystemExit("YUV420 crop offsets must be even.")
    if x < 0 or y < 0 or x + args.crop_width > args.src_width or y + args.crop_height > args.src_height:
        raise SystemExit("Crop rectangle is outside the source frame.")

    return x, y


def crop_yuv420(args):
    x, y = validate_args(args)
    src_y_size = args.src_width * args.src_height
    src_uv_size = args.src_width * args.src_height // 2
    src_frame_size = src_y_size + src_uv_size

    file_size = args.input.stat().st_size
    total_frames, remainder = divmod(file_size, src_frame_size)
    if remainder:
        raise SystemExit(
            f"Input size is not a multiple of one source frame: "
            f"{remainder} trailing bytes."
        )

    frames_to_write = total_frames if args.frames < 0 else min(args.frames, total_frames)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    print(f"input: {args.input}")
    print(f"output: {args.output}")
    print(f"source: {args.src_width}x{args.src_height}, frames: {total_frames}")
    print(f"crop: {args.crop_width}x{args.crop_height} at x={x}, y={y}")
    print(f"layout: {args.layout}")
    print(f"writing_frames: {frames_to_write}")

    uv_x = x // 2
    uv_y = y // 2
    uv_crop_width = args.crop_width // 2
    uv_crop_height = args.crop_height // 2

    with args.input.open("rb") as src, args.output.open("wb") as dst:
        for frame_idx in range(frames_to_write):
            y_bytes = src.read(src_y_size)
            uv_bytes = src.read(src_uv_size)
            if len(y_bytes) != src_y_size or len(uv_bytes) != src_uv_size:
                raise SystemExit(f"Unexpected EOF at frame {frame_idx}.")

            for row in range(y, y + args.crop_height):
                start = row * args.src_width + x
                dst.write(y_bytes[start:start + args.crop_width])

            if args.layout == "yuv420p":
                chroma_plane_size = (args.src_width // 2) * (args.src_height // 2)
                chroma_src_width = args.src_width // 2
                for plane_idx in range(2):
                    plane_offset = plane_idx * chroma_plane_size
                    for row in range(uv_y, uv_y + uv_crop_height):
                        start = plane_offset + row * chroma_src_width + uv_x
                        dst.write(uv_bytes[start:start + uv_crop_width])
            else:
                # NV12 has one interleaved UV row per 2 luma rows. Each chroma
                # row is as wide in bytes as the luma row.
                for row in range(uv_y, uv_y + uv_crop_height):
                    start = row * args.src_width + x
                    dst.write(uv_bytes[start:start + args.crop_width])

            if (frame_idx + 1) % 50 == 0 or frame_idx + 1 == frames_to_write:
                print(f"cropped {frame_idx + 1}/{frames_to_write} frames")


def main():
    args = parse_args()
    if not args.input.is_file():
        raise SystemExit(f"Input file not found: {args.input}")
    crop_yuv420(args)


if __name__ == "__main__":
    main()
