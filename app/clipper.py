from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple


HOOK_KEYWORDS = [
    "wow",
    "gila",
    "viral",
    "kaget",
    "ternyata",
    "fakta",
    "rahasia",
    "wajib",
    "jangan",
    "breaking",
    "terungkap",
]


@dataclass
class ClipSegment:
    start: float
    end: float
    score: int


def run_command(args: List[str]) -> str:
    env = os.environ.copy()
    # Prevent yt-dlp from reading implicit user-level config in hosted environments.
    env.setdefault("YTDLP_NO_CONFIG", "1")
    process = subprocess.run(args, capture_output=True, text=True, env=env)
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "Command failed")
    return process.stdout.strip()


def ffprobe_duration(video_path: Path) -> float:
    output = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )
    return float(output or 0.0)


def _existing_cookie_browser_attempts() -> List[List[str]]:
    candidates: List[Tuple[str, List[Path]]] = []
    home = Path.home()

    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            base = Path(local_app_data)
            candidates.extend(
                [
                    ("chrome", [base / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies"]),
                    ("edge", [base / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies"]),
                ]
            )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                ("chrome", [home / "Library" / "Application Support" / "Google" / "Chrome" / "Default" / "Cookies"]),
                ("edge", [home / "Library" / "Application Support" / "Microsoft Edge" / "Default" / "Cookies"]),
            ]
        )
    else:
        candidates.extend(
            [
                ("chrome", [home / ".config" / "google-chrome" / "Default" / "Cookies"]),
                ("edge", [home / ".config" / "microsoft-edge" / "Default" / "Cookies"]),
            ]
        )

    attempts: List[List[str]] = []
    for browser, paths in candidates:
        if any(path.exists() for path in paths):
            attempts.append(["--cookies-from-browser", browser])
    return attempts


def _should_use_browser_cookies() -> bool:
    # Safe-by-default: browser cookies are disabled unless explicitly enabled.
    enabled = os.getenv("YT_DLP_ENABLE_BROWSER_COOKIES", "").strip().lower()
    return enabled in {"1", "true", "yes", "on"}


def _is_cookie_db_error(message: str) -> bool:
    lowered = message.lower()
    return "cookies database" in lowered and "could not find" in lowered


def _available_js_runtimes() -> List[str]:
    runtimes: List[Tuple[str, str]] = [
        ("deno", "deno"),
        ("node", "node"),
        ("bun", "bun"),
        ("quickjs", "qjs"),
    ]
    return [runtime for runtime, executable in runtimes if shutil.which(executable)]


def download_video(video_url: str, download_dir: Path) -> Path:
    template = str(download_dir / "%(id)s.%(ext)s")
    ytdlp_cmd = [sys.executable, "-m", "yt_dlp"]
    js_runtime_args: List[str] = []
    js_runtimes = _available_js_runtimes()
    if js_runtimes:
        for runtime in js_runtimes:
            js_runtime_args.extend(["--js-runtimes", runtime])
    base_args = [
        *ytdlp_cmd,
        "--ignore-config",
        *js_runtime_args,
        "--no-playlist",
        "--geo-bypass",
        "--force-ipv4",
        "--extractor-retries",
        "5",
    ]

    attempts = [
        # Let yt-dlp auto select available formats first.
        [],
        # Prefer broadly available progressive MP4 first.
        ["-f", "18/b[ext=mp4]/b"],
        # Fallback to a broadly available pre-merged format.
        ["-f", "b"],
        # Try known web clients (no Android PO token requirement).
        [
            "--extractor-args",
            "youtube:player_client=web",
        ],
        [
            "--extractor-args",
            "youtube:player_client=web_safari",
        ],
        [
            "--extractor-args",
            "youtube:player_client=web_creator",
        ],
        [
            "--extractor-args",
            "youtube:player_client=ios",
        ],
        [
            "--extractor-args",
            "youtube:player_client=tv_embedded",
        ],
    ]
    if not js_runtimes:
        attempts.insert(1, ["--extractor-args", "youtube:player_skip=js"])
    # Local fallback using browser cookies only when it is explicitly viable.
    if _should_use_browser_cookies():
        attempts.extend(_existing_cookie_browser_attempts())

    last_error = "Unknown yt-dlp error"
    primary_error = ""
    for extra_args in attempts:
        try:
            output_path = run_command(
                [
                    *base_args,
                    *extra_args,
                    "-o",
                    template,
                    "--print",
                    "after_move:filepath",
                    video_url,
                ]
            )
            return Path(output_path)
        except RuntimeError as exc:
            current_error = str(exc)
            last_error = current_error
            if not primary_error and not _is_cookie_db_error(current_error):
                primary_error = current_error
            continue

    final_error = primary_error or last_error
    raise RuntimeError(
        "Gagal download video (format/signature YouTube dibatasi). "
        f"Detail terakhir: {final_error}"
    )


def download_subtitles(video_url: str, download_dir: Path) -> None:
    template = str(download_dir / "%(id)s.%(ext)s")
    run_command(
        [
            sys.executable,
            "-m",
            "yt_dlp",
            "--ignore-config",
            "--skip-download",
            "--write-auto-subs",
            "--write-subs",
            "--sub-langs",
            "id.*,en.*",
            "--convert-subs",
            "vtt",
            "-o",
            template,
            video_url,
        ]
    )


def find_subtitle_file(video_id: str, download_dir: Path) -> Path | None:
    patterns = [
        str(download_dir / f"{video_id}*.id*.vtt"),
        str(download_dir / f"{video_id}*.en*.vtt"),
        str(download_dir / f"{video_id}*.vtt"),
    ]
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            return Path(matches[0])
    return None


def timestamp_to_seconds(ts: str) -> float:
    parts = ts.replace(",", ".").split(":")
    if len(parts) == 3:
        h, m, s = parts
    elif len(parts) == 2:
        h, m, s = "0", parts[0], parts[1]
    else:
        return 0.0
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_vtt(vtt_path: Path) -> List[Tuple[float, float, str]]:
    rows: List[Tuple[float, float, str]] = []
    content = vtt_path.read_text(encoding="utf-8", errors="ignore")
    blocks = content.split("\n\n")
    time_re = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{3})\s-->\s(\d{2}:\d{2}:\d{2}\.\d{3})")

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        match = None
        text_lines: List[str] = []
        for line in lines:
            m = time_re.search(line)
            if m:
                match = m
                continue
            if "-->" not in line and "WEBVTT" not in line:
                text_lines.append(re.sub(r"<[^>]+>", "", line))
        if not match:
            continue
        text = " ".join(text_lines).strip()
        if not text:
            continue
        start = timestamp_to_seconds(match.group(1))
        end = timestamp_to_seconds(match.group(2))
        rows.append((start, end, text))
    return rows


def deduplicate_segments(segments: List[ClipSegment], min_gap: float = 2.0) -> List[ClipSegment]:
    segments = sorted(segments, key=lambda s: (s.start, -s.score))
    filtered: List[ClipSegment] = []
    for seg in segments:
        if not filtered or seg.start >= filtered[-1].end + min_gap:
            filtered.append(seg)
    return filtered


def pick_segments_from_subtitles(
    subtitle_rows: List[Tuple[float, float, str]],
    video_duration: float,
    clip_duration: int,
    max_clips: int,
) -> List[ClipSegment]:
    candidates: List[ClipSegment] = []
    for start, end, text in subtitle_rows:
        lowered = text.lower()
        score = sum(1 for keyword in HOOK_KEYWORDS if keyword in lowered)
        if score <= 0:
            continue
        clip_start = max(0.0, start - 1.2)
        clip_end = min(video_duration, clip_start + clip_duration)
        candidates.append(ClipSegment(start=clip_start, end=clip_end, score=score))

    candidates.sort(key=lambda x: (-x.score, x.start))
    unique = deduplicate_segments(candidates)
    if unique:
        return unique[:max_clips]
    return []


def pick_even_segments(video_duration: float, clip_duration: int, max_clips: int) -> List[ClipSegment]:
    if video_duration <= clip_duration:
        return [ClipSegment(start=0.0, end=video_duration, score=0)]

    step = (video_duration - clip_duration) / max(1, max_clips)
    segments: List[ClipSegment] = []
    for idx in range(max_clips):
        start = idx * step
        end = min(video_duration, start + clip_duration)
        segments.append(ClipSegment(start=start, end=end, score=0))
    return segments


def render_vertical_clip(source_video: Path, target_video: Path, start: float, end: float) -> None:
    profiles = [
        {
            "codec": "h264_amf",
            "vf": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24",
            "preset": "speed",
            "audio_bitrate": "96k",
            "threads": "1",
            "extra": [],
        },
        {
            "codec": "libx264",
            "vf": "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
            "preset": "veryfast",
            "crf": "23",
            "audio_bitrate": "128k",
            "threads": "2",
            "extra": [],
        },
        {
            "codec": "libx264",
            "vf": "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24",
            "preset": "ultrafast",
            "crf": "28",
            "audio_bitrate": "96k",
            "threads": "1",
            "extra": ["-tune", "zerolatency", "-x264-params", "ref=1:rc-lookahead=0:subme=0:me=dia"],
        },
        {
            "codec": "libx264",
            "vf": "scale=540:960:force_original_aspect_ratio=increase,crop=540:960,fps=20",
            "preset": "ultrafast",
            "crf": "32",
            "audio_bitrate": "64k",
            "threads": "1",
            "extra": ["-tune", "zerolatency", "-x264-params", "ref=1:rc-lookahead=0:subme=0:me=dia"],
        },
    ]

    last_error = "Unknown ffmpeg error"
    for profile in profiles:
        try:
            run_command(
                [
                    "ffmpeg",
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-to",
                    f"{end:.3f}",
                    "-i",
                    str(source_video),
                    "-vf",
                    profile["vf"],
                    "-c:v",
                    profile["codec"],
                    "-preset",
                    profile["preset"],
                    *([] if profile["codec"] == "h264_amf" else ["-crf", profile["crf"]]),
                    "-threads",
                    profile["threads"],
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-b:a",
                    profile["audio_bitrate"],
                    *profile["extra"],
                    "-movflags",
                    "+faststart",
                    str(target_video),
                ]
            )
            return
        except RuntimeError as exc:
            last_error = str(exc)
            continue

    raise RuntimeError(f"Gagal render clip setelah fallback profil encode: {last_error}")


def build_clips_for_video(
    video_id: str,
    video_url: str,
    download_dir: Path,
    output_dir: Path,
    clip_duration: int = 30,
    max_clips: int = 3,
) -> List[Path]:
    source_video = download_video(video_url, download_dir)
    video_duration = ffprobe_duration(source_video)

    subtitle_rows: List[Tuple[float, float, str]] = []
    try:
        download_subtitles(video_url, download_dir)
        subtitle_file = find_subtitle_file(video_id, download_dir)
        if subtitle_file:
            subtitle_rows = parse_vtt(subtitle_file)
    except Exception:
        subtitle_rows = []

    picked = pick_segments_from_subtitles(
        subtitle_rows=subtitle_rows,
        video_duration=video_duration,
        clip_duration=clip_duration,
        max_clips=max_clips,
    )
    if not picked:
        picked = pick_even_segments(video_duration, clip_duration, max_clips)

    produced: List[Path] = []
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", video_id)
    for idx, segment in enumerate(picked, start=1):
        out_path = output_dir / f"{safe_id}_clip_{idx:02d}.mp4"
        render_vertical_clip(source_video, out_path, segment.start, segment.end)
        produced.append(out_path)
    return produced


def build_clips_for_local_file(
    source_video: Path,
    source_id: str,
    output_dir: Path,
    clip_duration: int = 30,
    max_clips: int = 3,
) -> List[Path]:
    video_duration = ffprobe_duration(source_video)
    picked = pick_even_segments(video_duration, clip_duration, max_clips)

    produced: List[Path] = []
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", source_id)
    for idx, segment in enumerate(picked, start=1):
        out_path = output_dir / f"{safe_id}_upload_clip_{idx:02d}.mp4"
        render_vertical_clip(source_video, out_path, segment.start, segment.end)
        produced.append(out_path)
    return produced
