from __future__ import annotations

import glob
import os
import re
import subprocess
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
    process = subprocess.run(args, capture_output=True, text=True)
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


def download_video(video_url: str, download_dir: Path) -> Path:
    template = str(download_dir / "%(id)s.%(ext)s")
    attempts = [
        # Use web client to avoid Android PO-token requirement.
        [
            "--extractor-args",
            "youtube:player_client=web",
            "-f",
            "b/bv*+ba",
            "--remux-video",
            "mp4",
        ],
        [
            "--extractor-args",
            "youtube:player_client=web_safari",
            "-f",
            "b/bv*+ba",
            "--remux-video",
            "mp4",
        ],
        [
            "--extractor-args",
            "youtube:player_client=web_creator",
            "-f",
            "b/bv*+ba",
            "--remux-video",
            "mp4",
        ],
        # Last fallback: let yt-dlp auto select.
        [],
    ]

    last_error = "Unknown yt-dlp error"
    for extra_args in attempts:
        try:
            output_path = run_command(
                [
                    "yt-dlp",
                    "--no-playlist",
                    "--geo-bypass",
                    "--geo-bypass-country",
                    "ID",
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
            last_error = str(exc)
            continue

    raise RuntimeError(
        "Gagal download video (YouTube membatasi akses dari server cloud/403). "
        f"Detail terakhir: {last_error}"
    )


def download_subtitles(video_url: str, download_dir: Path) -> None:
    template = str(download_dir / "%(id)s.%(ext)s")
    run_command(
        [
            "yt-dlp",
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
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "fps=30"
    )
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
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(target_video),
        ]
    )


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
