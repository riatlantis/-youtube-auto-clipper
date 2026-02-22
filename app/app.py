from __future__ import annotations

import os
from pathlib import Path
from typing import List

import streamlit as st

from clipper import build_clips_for_local_file, build_clips_for_video
from config import (
    DEFAULT_CATEGORY,
    DEFAULT_REGION,
    DOWNLOAD_DIR,
    OUTPUT_DIR,
    YOUTUBE_API_KEY,
)
from youtube_service import TrendingVideo, fetch_top_viewed_recent_videos


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


def render_download_section() -> None:
    st.divider()
    st.markdown("### Download Hasil")

    clip_results = st.session_state.get("clip_results", [])
    if not clip_results:
        st.info("Belum ada clip yang bisa di-download.")
        return

    for clip_path_str in clip_results:
        clip_path = Path(clip_path_str)
        if not clip_path.exists():
            continue
        with clip_path.open("rb") as file_handle:
            st.download_button(
                label=f"Download {clip_path.name}",
                data=file_handle.read(),
                file_name=clip_path.name,
                mime="video/mp4",
                key=f"dl_{clip_path.name}",
            )


def render_trending_mode(
    api_key: str,
    days_back: int,
    top_n: int,
    max_duration: int,
    clip_duration: int,
    clips_per_video: int,
) -> None:
    if "trending_cache" not in st.session_state:
        st.session_state.trending_cache = []

    can_run = bool(api_key)
    if st.button("1) Load Trending", disabled=not can_run):
        with st.spinner("Mencari video paling banyak ditonton..."):
            try:
                videos = fetch_top_viewed_recent_videos(
                    api_key=api_key,
                    days_back=days_back,
                    max_results=top_n,
                    min_duration_seconds=60,
                    max_duration_seconds=max_duration * 60,
                    region_code=DEFAULT_REGION,
                    category_id=DEFAULT_CATEGORY,
                )
                st.session_state.trending_cache = videos
                if videos:
                    st.success(f"Dapat {len(videos)} video teratas (1-{days_back} hari terakhir).")
                else:
                    st.warning(
                        "Tidak ada hasil. Coba ubah rentang hari atau naikkan batas durasi video."
                    )
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
                collected: List[str] = []
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
                        collected.extend([str(clip) for clip in clips])
                        for clip in clips:
                            st.write(f"OK: `{clip.name}`")
                            with st.expander(f"Preview {clip.name}"):
                                st.video(str(clip))
                    except Exception as exc:
                        failed += 1
                        st.error(f"Gagal proses {video.title}: {exc}")
            st.session_state["clip_results"] = collected
            st.success(f"Selesai. Total clip: {total}. Video gagal: {failed}.")


def render_upload_mode(clip_duration: int, clips_per_video: int) -> None:
    st.info("Mode ini paling stabil untuk Streamlit Cloud. Upload file video, lalu app akan potong otomatis.")
    upload = st.file_uploader("Upload video", type=["mp4", "mov", "m4v", "webm"])

    if st.button("Generate Clips dari Upload", type="primary"):
        if upload is None:
            st.warning("Upload 1 file video dulu.")
            return

        source_path = Path(DOWNLOAD_DIR) / f"upload_{upload.name}"
        source_path.write_bytes(upload.getbuffer())

        with st.spinner("Memproses upload jadi short clips..."):
            try:
                clips = build_clips_for_local_file(
                    source_video=source_path,
                    source_id=upload.name,
                    output_dir=Path(OUTPUT_DIR),
                    clip_duration=clip_duration,
                    max_clips=clips_per_video,
                )
                st.session_state["clip_results"] = [str(clip) for clip in clips]
                for clip in clips:
                    st.write(f"OK: `{clip.name}`")
                    with st.expander(f"Preview {clip.name}"):
                        st.video(str(clip))
                st.success(f"Selesai. Total clip: {len(clips)}.")
            except Exception as exc:
                st.error(f"Gagal proses upload: {exc}")


def main() -> None:
    st.title("YouTube Trending -> Auto Shorts Clipper")
    st.caption("Cari video paling banyak ditonton 1-7 hari terakhir, lalu potong jadi klip vertikal 9:16.")

    is_cloud = bool(os.getenv("STREAMLIT_SHARING_MODE"))
    default_index = 1 if is_cloud else 0
    mode = st.radio(
        "Mode Sumber",
        ["YouTube Trending", "Upload MP4 (Cloud Safe)"],
        horizontal=True,
        index=default_index,
    )

    if is_cloud and mode == "YouTube Trending":
        st.warning("Di Streamlit Cloud, download YouTube bisa gagal (403/signature). Gunakan mode Upload untuk hasil stabil.")

    col1, col2, col3 = st.columns(3)
    with col1:
        days_back = st.slider("Rentang hari", min_value=1, max_value=7, value=3)
    with col2:
        top_n = st.slider("Ambil top video", min_value=1, max_value=20, value=5)
    with col3:
        clips_per_video = st.slider("Clip/video", min_value=1, max_value=5, value=2)

    clip_duration = st.slider("Durasi per clip (detik)", min_value=10, max_value=60, value=30)
    max_duration = st.slider("Maks durasi video sumber (menit)", min_value=2, max_value=60, value=20)

    api_key = ensure_api_key()

    if mode == "YouTube Trending":
        render_trending_mode(api_key, days_back, top_n, max_duration, clip_duration, clips_per_video)
    else:
        render_upload_mode(clip_duration, clips_per_video)

    render_download_section()


if __name__ == "__main__":
    main()
