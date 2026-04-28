#!/usr/bin/env python3
"""Convert a raw YUV file into an MP4 video using ffmpeg.

Raw YUV files do not store width, height, or frame rate, so those values must
come from the dataset or recording context. This wrapper accepts either
``--width/--height`` or ``--video-size WxH`` and uses a local ffmpeg binary
from ``imageio-ffmpeg`` when system ffmpeg is unavailable.
"""

import argparse
import shutil
import subprocess
from pathlib import Path

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a raw YUV file to MP4 with ffmpeg."
    )
    parser.add_argument("input_yuv", type=Path, help="Path to the raw input .yuv file")
    parser.add_argument("output_mp4", type=Path, help="Path to the output .mp4 file")
    parser.add_argument("--width", type=int, help="Input width")
    parser.add_argument("--height", type=int, help="Input height")
    parser.add_argument(
        "--video-size",
        type=str,
        help="Input resolution in WxH form, for example 3840x2160",
    )
    parser.add_argument(
        "--output-width",
        type=int,
        help="Optional output width. Defaults to the input width.",
    )
    parser.add_argument(
        "--output-height",
        type=int,
        help="Optional output height. Defaults to the input height.",
    )
    parser.add_argument(
        "--fps",
        "--framerate",
        dest="fps",
        type=float,
        default=30.0,
        help="Input frame rate. Default: 30",
    )
    parser.add_argument(
        "--pix-fmt",
        "--pixel-format",
        dest="pix_fmt",
        default="yuv420p",
        help="Raw input pixel format for ffmpeg. Default: yuv420p",
    )
    parser.add_argument(
        "--codec",
        default="libx264",
        help="Video codec for MP4 output. Default: libx264",
    )
    parser.add_argument(
        "--qp",
        type=int,
        default=0,
        help="Constant quantizer for libx264-style encoders. Default: 0",
    )
    parser.add_argument(
        "--preset",
        default="medium",
        help="Encoder preset when supported by the codec. Default: medium",
    )
    parser.add_argument(
        "--output-pix-fmt",
        default="yuv420p",
        help="Output pixel format in the MP4. Default: yuv420p",
    )
    parser.add_argument(
        "--loglevel",
        default="error",
        help="ffmpeg loglevel. Default: error",
    )
    return parser.parse_args()


def ensure_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path is not None:
        return ffmpeg_path
    if imageio_ffmpeg is not None:
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise SystemExit("ffmpeg not found on PATH, and imageio-ffmpeg is not installed.")


def resolve_input_size(args):
    width = args.width
    height = args.height

    if args.video_size:
        try:
            width_str, height_str = args.video_size.lower().split("x", maxsplit=1)
            parsed_width = int(width_str)
            parsed_height = int(height_str)
        except ValueError as exc:
            raise SystemExit("--video-size must be in WxH form, for example 3840x2160.") from exc

        if width is not None and width != parsed_width:
            raise SystemExit("--width conflicts with --video-size.")
        if height is not None and height != parsed_height:
            raise SystemExit("--height conflicts with --video-size.")
        width = parsed_width
        height = parsed_height

    if width is None or height is None:
        raise SystemExit(
            "Please provide the raw input resolution with --width/--height or --video-size."
        )

    return width, height


def validate_args(args):
    if not args.input_yuv.is_file():
        raise SystemExit(f"Input file not found: {args.input_yuv}")
    args.width, args.height = resolve_input_size(args)
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("Width and height must be positive integers.")
    if args.width % 2 != 0 or args.height % 2 != 0:
        raise SystemExit("YUV420 requires even width and height.")
    if args.output_width is not None and args.output_width <= 0:
        raise SystemExit("Output width must be a positive integer.")
    if args.output_height is not None and args.output_height <= 0:
        raise SystemExit("Output height must be a positive integer.")
    if args.output_width is None and args.output_height is not None:
        raise SystemExit("Please provide both --output-width and --output-height.")
    if args.output_width is not None and args.output_height is None:
        raise SystemExit("Please provide both --output-width and --output-height.")
    if args.output_width is not None and args.output_width % 2 != 0:
        raise SystemExit("Output width must be even for yuv420p output.")
    if args.output_height is not None and args.output_height % 2 != 0:
        raise SystemExit("Output height must be even for yuv420p output.")
    if args.fps <= 0:
        raise SystemExit("FPS must be positive.")
    if args.output_mp4.suffix.lower() != ".mp4":
        raise SystemExit("Output path must end with .mp4")
    if args.output_pix_fmt.endswith("420p"):
        if args.output_width is not None and args.output_width % 2 != 0:
            raise SystemExit("Output width must be even for 4:2:0 output.")
        if args.output_height is not None and args.output_height % 2 != 0:
            raise SystemExit("Output height must be even for 4:2:0 output.")


def build_command(args, ffmpeg_path):
    cmd = [
        ffmpeg_path,
        "-v",
        args.loglevel,
        "-y",
        "-f",
        "rawvideo",
        "-video_size",
        f"{args.width}x{args.height}",
        "-pixel_format",
        args.pix_fmt,
        "-framerate",
        f"{args.fps}",
        "-i",
        str(args.input_yuv),
        "-an",
    ]

    if args.output_width is not None:
        cmd.extend(["-vf", f"scale={args.output_width}:{args.output_height}"])

    cmd.extend(["-c:v", args.codec])

    if args.codec.startswith("libx264"):
        cmd.extend(["-preset", args.preset, "-qp", str(args.qp)])

    cmd.extend(
        [
            "-movflags",
            "+faststart",
            "-pix_fmt",
            args.output_pix_fmt,
            str(args.output_mp4),
        ]
    )
    return cmd


def main():
    args = parse_args()
    validate_args(args)
    ffmpeg_path = ensure_ffmpeg()

    args.output_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = build_command(args, ffmpeg_path)
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        quoted = " ".join(str(part) for part in cmd)
        raise SystemExit(f"ffmpeg failed with exit code {exc.returncode}: {quoted}") from exc

    print(f"wrote_mp4: {args.output_mp4}")
    print(f"input_format: {args.pix_fmt}")
    if args.output_width is not None:
        print(f"input_resolution: {args.width}x{args.height}")
        print(f"output_resolution: {args.output_width}x{args.output_height}")
    else:
        print(f"resolution: {args.width}x{args.height}")
    print(f"fps: {args.fps}")


if __name__ == "__main__":
    main()
