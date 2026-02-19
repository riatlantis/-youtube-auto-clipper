from __future__ import annotations

from pathlib import Path
from typing import List

import streamlit as st

from clipper import build_clips_for_video
from config import (
    DEFAULT_CATEGORY,
    DEFAULT_REGION,
    DOWNLOAD_DIR,
    OUTPUT_DIR,
    YOUTUBE_API_KEY,
)
from youtube_service import TrendingVideo, fetch_trending_videos

def ensure_api_key() -> str:
    api_key = st.text_input(
        "YouTube API Key",
        value=YOUTUBE_API_KEY,
        type="password",
        help="Buat di Google Cloud Console > YouTube Data API v3",
    )
    if not api_key:
        st.warning("Isi YouTube API Key dulu agar data trending bisa diambil.")
    return api_key


def format_video_row(video: TrendingVideo) -> str:
    minutes = video.duration_seconds // 60
    seconds = video.duration_seconds % 60
    return (
        f"{video.title} | {video.channel} | "
        f"{video.views:,} views | {minutes:02d}:{seconds:02d}"
    )


def main() -> None:
    st.title("YouTube Trending -> Auto Shorts Clipper")
    st.caption("Ambil video trending, lalu potong otomatis jadi klip vertikal 9:16.")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        region = st.text_input("Region", value=DEFAULT_REGION, max_chars=2).upper()
    with col2:
        category = st.text_input("Category ID", value=DEFAULT_CATEGORY, max_chars=4)
    with col3:
        top_n = st.slider("Ambil top video", min_value=1, max_value=20, value=5)
    with col4:
        clips_per_video = st.slider("Clip/video", min_value=1, max_value=5, value=2)

    clip_duration = st.slider("Durasi per clip (detik)", min_value=10, max_value=60, value=30)
    max_duration = st.slider("Maks durasi video sumber (menit)", min_value=2, max_value=60, value=20)

    api_key = ensure_api_key()
    can_run = bool(api_key)

    if "trending_cache" not in st.session_state:
        st.session_state.trending_cache = []

    if st.button("1) Load Trending", disabled=not can_run):
        with st.spinner("Mengambil video trending..."):
            try:
                videos = fetch_trending_videos(
                    api_key=api_key,
                    region_code=region,
                    category_id=category,
                    max_results=top_n,
                    min_duration_seconds=60,
                    max_duration_seconds=max_duration * 60,
                )
                st.session_state.trending_cache = videos
                st.success(f"Dapat {len(videos)} video trending.")
            except Exception as exc:
                st.error(f"Gagal mengambil trending: {exc}")

    trending: List[TrendingVideo] = st.session_state.trending_cache
    if trending:
        options = {format_video_row(v): v for v in trending}
        selected_rows = st.multiselect(
            "2) Pilih video untuk dipotong",
            list(options.keys()),
            default=list(options.keys())[: min(3, len(options))],
        )

        if st.button("3) Generate Clips", type="primary"):
            if not selected_rows:
                st.warning("Pilih minimal 1 video.")
                return
            selected_videos = [options[row] for row in selected_rows]
            with st.spinner("Generate clip berjalan..."):
                total = 0
                failed = 0
                for video in selected_videos:
                    try:
                        video_url = f"https://www.youtube.com/watch?v={video.video_id}"
                        clips = build_clips_for_video(
                            video_id=video.video_id,
                            video_url=video_url,
                            download_dir=Path(DOWNLOAD_DIR),
                            output_dir=Path(OUTPUT_DIR),
                            clip_duration=clip_duration,
                            max_clips=clips_per_video,
                        )
                        total += len(clips)
                        for clip in clips:
                            st.write(f"OK: `{clip.name}`")
                            with st.expander(f"Preview {clip.name}"):
                                st.video(str(clip))
                    except Exception as exc:
                        failed += 1
                        st.error(f"Gagal proses {video.title}: {exc}")
            st.success(f"Selesai. Total clip: {total}. Video gagal: {failed}.")

    st.divider()
    st.markdown("### Folder Output")
    st.code(str(OUTPUT_DIR))
    st.info("Pastikan `ffmpeg`, `ffprobe`, dan `yt-dlp` tersedia di PATH sistem.")


if __name__ == "__main__":
    main()
