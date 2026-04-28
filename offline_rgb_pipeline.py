#!/usr/bin/env python3
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


DEFAULT_SINGLE_RATE_QP = 32


def parse_args():
    parser = argparse.ArgumentParser(
        description="Offline RGB video pipeline for DCVC-RT using extracted PNG frames."
    )
    parser.add_argument("--input_video", type=Path, required=True,
                        help="Path to the input MP4/MKV video.")
    parser.add_argument("--work_dir", type=Path, required=True,
                        help="Working directory for extracted frames, configs, bitstreams, and logs.")
    parser.add_argument("--model_path_i", type=Path, required=True,
                        help="Path to the DCVC-RT intra-frame checkpoint.")
    parser.add_argument("--model_path_p", type=Path, required=True,
                        help="Path to the DCVC-RT video checkpoint.")
    parser.add_argument("--rate_num", type=int, default=1,
                        help="Number of rate points to run. Default: 1.")
    parser.add_argument("--force_frame_num", type=int, default=-1,
                        help="Optional frame limit. Default: full video.")
    parser.add_argument("--force_intra_period", type=int, default=-1,
                        help="Optional intra period override. Default: -1.")
    parser.add_argument("--output_video", type=Path, required=True,
                        help="Path for the reconstructed output video.")
    parser.add_argument("--cuda", type=int, default=1,
                        help="Pass 1 to use CUDA, 0 for CPU. Default: 1.")
    parser.add_argument("--worker", "-w", type=int, default=1,
                        help="Worker count passed to test_video.py. Default: 1.")
    parser.add_argument("--reset_interval", type=int, default=64,
                        help="Reset interval passed to test_video.py. Default: 64.")
    parser.add_argument("--force_zero_thres", type=float, default=0.12,
                        help="Threshold passed to test_video.py. Default: 0.12.")
    parser.add_argument("--verbose", type=int, default=1,
                        help="Verbosity passed to test_video.py. Default: 1.")
    parser.add_argument("--qp_i", type=int, nargs="+",
                        help="Optional explicit I-frame QP list.")
    parser.add_argument("--qp_p", type=int, nargs="+",
                        help="Optional explicit P-frame QP list.")
    parser.add_argument("--ffmpeg_loglevel", type=str, default="error",
                        help="ffmpeg/ffprobe loglevel. Default: error.")
    return parser.parse_args()


def resolve_ffmpeg_exe():
    ffmpeg_exe = shutil.which("ffmpeg")
    if ffmpeg_exe is not None:
        return ffmpeg_exe
    if imageio_ffmpeg is not None:
        return imageio_ffmpeg.get_ffmpeg_exe()
    raise SystemExit(
        "Neither system ffmpeg nor Python package imageio-ffmpeg is available."
    )


def run_command(cmd, env=None):
    try:
        subprocess.run(cmd, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        quoted = " ".join(str(part) for part in cmd)
        raise SystemExit(f"Command failed ({exc.returncode}): {quoted}") from exc


def probe_video(input_video):
    if imageio_ffmpeg is None:
        raise SystemExit(
            "Python package imageio-ffmpeg is required to probe videos in this environment."
        )

    reader = imageio_ffmpeg.read_frames(str(input_video))
    try:
        meta = next(reader)
    finally:
        reader.close()

    width, height = meta["size"]
    fps_value = meta.get("fps")
    if fps_value is None or fps_value <= 0:
        raise SystemExit(f"Invalid frame rate reported for {input_video}: {fps_value}")

    fps_fraction = Fraction(str(fps_value)).limit_denominator(1000)
    frame_count = None
    try:
        frame_count, _ = imageio_ffmpeg.count_frames_and_secs(str(input_video))
    except Exception:
        frame_count = None

    return {
        "width": width,
        "height": height,
        "fps_fraction": fps_fraction,
        "fps_string": f"{fps_fraction.numerator}/{fps_fraction.denominator}",
        "frame_count": frame_count,
    }


def count_extracted_frames(frame_dir):
    return len(list(frame_dir.glob("im*.png")))


def extract_png_frames(input_video, frame_dir, frame_limit, loglevel, ffmpeg_exe):
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True, exist_ok=True)
    output_pattern = frame_dir / "im%05d.png"
    cmd = [
        ffmpeg_exe,
        "-v", loglevel,
        "-y",
        "-i", str(input_video),
        "-start_number", "1",
    ]
    if frame_limit > 0:
        cmd.extend(["-frames:v", str(frame_limit)])
    cmd.append(str(output_pattern))
    run_command(cmd)


def write_test_config(config_path, frame_root, sequence_name, width, height, frame_count,
                      intra_period):
    config = {
        "root_path": str(frame_root),
        "test_classes": {
            "D405_RGB": {
                "test": 1,
                "base_path": "",
                "src_type": "png",
                "sequences": {
                    sequence_name: {
                        "width": width,
                        "height": height,
                        "frames": frame_count,
                        "intra_period": intra_period,
                    }
                },
            }
        },
    }
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fp:
        json.dump(config, fp, indent=2)


def default_intra_period(frame_count, force_intra_period):
    if force_intra_period > 0:
        return force_intra_period
    return max(1, frame_count)


def build_test_video_command(args, repo_root, config_path, stream_path, output_json):
    cmd = [
        sys.executable,
        str(repo_root / "test_video.py"),
        "--model_path_i", str(args.model_path_i),
        "--model_path_p", str(args.model_path_p),
        "--rate_num", str(args.rate_num),
        "--test_config", str(config_path),
        "--cuda", str(args.cuda),
        "-w", str(args.worker),
        "--write_stream", "1",
        "--save_decoded_frame", "1",
        "--force_zero_thres", str(args.force_zero_thres),
        "--output_path", str(output_json),
        "--force_intra_period", str(args.force_intra_period),
        "--reset_interval", str(args.reset_interval),
        "--force_frame_num", str(args.force_frame_num),
        "--check_existing", "0",
        "--verbose", str(args.verbose),
        "--stream_path", str(stream_path),
    ]
    qp_i = args.qp_i
    qp_p = args.qp_p
    if args.rate_num == 1 and qp_i is None:
        qp_i = [DEFAULT_SINGLE_RATE_QP]
    if args.rate_num == 1 and qp_p is None:
        qp_p = qp_i
    if qp_i is not None:
        cmd.extend(["--qp_i", *[str(value) for value in qp_i]])
    if qp_p is not None:
        cmd.extend(["--qp_p", *[str(value) for value in qp_p]])
    return cmd


def build_test_video_env():
    env = os.environ.copy()
    candidate_prefixes = []
    for raw_prefix in (
        env.get("CONDA_PREFIX"),
        sys.prefix,
        str(Path(sys.executable).resolve().parent.parent),
    ):
        if raw_prefix:
            prefix = Path(raw_prefix).resolve()
            if prefix not in candidate_prefixes:
                candidate_prefixes.append(prefix)

    conda_lib = None
    libstdcpp = None
    for prefix in candidate_prefixes:
        candidate_lib = prefix / "lib"
        candidate_libstdcpp = candidate_lib / "libstdc++.so.6"
        if candidate_libstdcpp.is_file():
            conda_lib = candidate_lib
            libstdcpp = candidate_libstdcpp
            break

    if conda_lib is None or libstdcpp is None:
        return env

    env["LD_LIBRARY_PATH"] = (
        f"{conda_lib}:{env['LD_LIBRARY_PATH']}"
        if env.get("LD_LIBRARY_PATH")
        else str(conda_lib)
    )
    env["LD_PRELOAD"] = (
        f"{libstdcpp}:{env['LD_PRELOAD']}"
        if env.get("LD_PRELOAD")
        else str(libstdcpp)
    )
    env.setdefault("DCVC_DISABLE_CUSTOM_CUDA", "1")
    return env


def run_test_video_command(cmd):
    env = build_test_video_env()
    ld_library_path = env.get("LD_LIBRARY_PATH", "")
    ld_preload = env.get("LD_PRELOAD", "")
    shell_cmd = (
        f"export LD_LIBRARY_PATH={shlex.quote(ld_library_path)}; "
        f"export LD_PRELOAD={shlex.quote(ld_preload)}; "
        f"exec {' '.join(shlex.quote(str(part)) for part in cmd)}"
    )
    run_command(["bash", "-lc", shell_cmd], env=env)


def load_rate_results(output_json):
    with output_json.open("r", encoding="utf-8") as fp:
        data = json.load(fp)
    class_results = data["D405_RGB"]
    sequence_name, sequence_results = next(iter(class_results.items()))
    ordered = [sequence_results[key] for key in sorted(sequence_results.keys())]
    return sequence_name, ordered


def output_path_for_rate(base_output, rate_result, total_rates):
    if rate_result["rate_idx"] == 0 and total_rates == 1:
        return base_output
    suffix = f"_rate{rate_result['rate_idx']:03d}_q{rate_result['qp_i']}"
    return base_output.with_name(f"{base_output.stem}{suffix}{base_output.suffix}")


def assemble_video(frame_dir, output_video, fps_string, loglevel, ffmpeg_exe):
    output_video.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_exe,
        "-v", loglevel,
        "-y",
        "-framerate", fps_string,
        "-start_number", "1",
        "-i", str(frame_dir / "im%05d.png"),
        "-pix_fmt", "yuv420p",
        str(output_video),
    ]
    run_test_video_command(cmd)


def write_manifest(manifest_path, input_video, extracted_frame_count, probe, config_path,
                   output_json, rate_results, packaged_videos):
    manifest = {
        "input_video": str(input_video),
        "width": probe["width"],
        "height": probe["height"],
        "fps": probe["fps_string"],
        "extracted_frame_count": extracted_frame_count,
        "config_path": str(config_path),
        "metrics_json": str(output_json),
        "rates": [],
    }
    for rate_result, video_path in zip(rate_results, packaged_videos):
        manifest["rates"].append({
            "rate_idx": rate_result["rate_idx"],
            "qp_i": rate_result["qp_i"],
            "qp_p": rate_result["qp_p"],
            "bitstream_path": rate_result["bitstream_path"],
            "metrics_path": rate_result["metrics_path"],
            "decoded_frame_path": rate_result["decoded_frame_path"],
            "reconstructed_video": str(video_path),
        })
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as fp:
        json.dump(manifest, fp, indent=2)


def validate_args(args):
    if args.rate_num < 1:
        raise SystemExit("--rate_num must be >= 1")
    if args.force_frame_num == 0 or args.force_frame_num < -1:
        raise SystemExit("--force_frame_num must be -1 or a positive integer")
    if args.force_intra_period == 0 or args.force_intra_period < -1:
        raise SystemExit("--force_intra_period must be -1 or a positive integer")
    if args.qp_i is not None and len(args.qp_i) != args.rate_num:
        raise SystemExit("--qp_i length must match --rate_num")
    if args.qp_p is not None and len(args.qp_p) != args.rate_num:
        raise SystemExit("--qp_p length must match --rate_num")


def main():
    args = parse_args()
    validate_args(args)

    repo_root = Path(__file__).resolve().parent
    ffmpeg_exe = resolve_ffmpeg_exe()

    input_video = args.input_video.resolve()
    if not input_video.is_file():
        raise SystemExit(f"Input video not found: {input_video}")
    if not args.model_path_i.is_file():
        raise SystemExit(f"Model checkpoint not found: {args.model_path_i}")
    if not args.model_path_p.is_file():
        raise SystemExit(f"Model checkpoint not found: {args.model_path_p}")

    work_dir = args.work_dir.resolve()
    sequence_name = input_video.stem
    frame_root = work_dir / "frames"
    frame_dir = frame_root / sequence_name
    config_path = work_dir / "configs" / f"{sequence_name}_png.json"
    stream_path = work_dir / "streams"
    output_json = work_dir / "logs" / "output.json"
    manifest_path = work_dir / "logs" / "manifest.json"

    probe = probe_video(input_video)
    extract_png_frames(
        input_video, frame_dir, args.force_frame_num, args.ffmpeg_loglevel, ffmpeg_exe
    )
    extracted_frame_count = count_extracted_frames(frame_dir)
    if extracted_frame_count == 0:
        raise SystemExit(f"No PNG frames were extracted from {input_video}")

    if args.force_frame_num > 0:
        expected_frames = min(args.force_frame_num, extracted_frame_count)
    elif probe["frame_count"] is not None:
        expected_frames = min(probe["frame_count"], extracted_frame_count)
    else:
        expected_frames = extracted_frame_count

    intra_period = default_intra_period(expected_frames, args.force_intra_period)
    write_test_config(
        config_path=config_path,
        frame_root=frame_root,
        sequence_name=sequence_name,
        width=probe["width"],
        height=probe["height"],
        frame_count=expected_frames,
        intra_period=intra_period,
    )

    cmd = build_test_video_command(args, repo_root, config_path, stream_path, output_json)
    run_command(cmd)

    loaded_sequence_name, rate_results = load_rate_results(output_json)
    if loaded_sequence_name != sequence_name:
        raise SystemExit(
            f"Unexpected sequence name in output JSON: {loaded_sequence_name} != {sequence_name}"
        )

    global len_suffix_safe_results
    len_suffix_safe_results = len(rate_results)

    packaged_videos = []
    for rate_result in rate_results:
        frame_output_dir = Path(rate_result["decoded_frame_path"])
        if not frame_output_dir.is_dir():
            raise SystemExit(f"Decoded frame directory not found: {frame_output_dir}")
        decoded_frame_count = count_extracted_frames(frame_output_dir)
        if decoded_frame_count != expected_frames:
            raise SystemExit(
                f"Decoded frame count mismatch for {frame_output_dir}: "
                f"{decoded_frame_count} != {expected_frames}"
            )
        output_video = output_path_for_rate(
            args.output_video.resolve(), rate_result, len(rate_results)
        )
        assemble_video(
            frame_output_dir, output_video, probe["fps_string"], args.ffmpeg_loglevel, ffmpeg_exe
        )
        packaged_videos.append(output_video)

    write_manifest(
        manifest_path=manifest_path,
        input_video=input_video,
        extracted_frame_count=expected_frames,
        probe=probe,
        config_path=config_path,
        output_json=output_json,
        rate_results=rate_results,
        packaged_videos=packaged_videos,
    )

    print("Offline DCVC-RT pipeline finished.")
    print(f"Frames: {expected_frames}")
    print(f"Config: {config_path}")
    print(f"Metrics JSON: {output_json}")
    print(f"Manifest: {manifest_path}")
    for video_path in packaged_videos:
        print(f"Reconstructed video: {video_path}")


if __name__ == "__main__":
    main()
