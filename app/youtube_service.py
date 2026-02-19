from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List

from googleapiclient.discovery import build


@dataclass
class TrendingVideo:
    video_id: str
    title: str
    channel: str
    views: int
    duration_seconds: int
    published_at: str
    score: float = 0.0


_ISO_DURATION_RE = re.compile(
    r"^P(?:\d+Y)?(?:\d+M)?(?:\d+W)?(?:\d+D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$"
)


def parse_iso8601_duration(value: str) -> int:
    match = _ISO_DURATION_RE.match(value)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def fetch_trending_videos(
    api_key: str,
    region_code: str = "ID",
    category_id: str = "24",
    max_results: int = 10,
    min_duration_seconds: int = 60,
    max_duration_seconds: int = 2400,
) -> List[TrendingVideo]:
    youtube = build("youtube", "v3", developerKey=api_key)

    def _query(category: str | None) -> dict:
        params = {
            "part": "snippet,statistics,contentDetails",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
        }
        if category:
            params["videoCategoryId"] = category
        return youtube.videos().list(**params).execute()

    response = _query(category_id.strip() or None)
    # Fallback: beberapa region/category bisa kosong.
    if not response.get("items"):
        response = _query(None)

    filtered_results: List[TrendingVideo] = []
    unfiltered_results: List[TrendingVideo] = []
    for item in response.get("items", []):
        duration = parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "PT0S"))

        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        video = TrendingVideo(
            video_id=item.get("id", ""),
            title=snippet.get("title", ""),
            channel=snippet.get("channelTitle", ""),
            views=int(stats.get("viewCount", 0)),
            duration_seconds=duration,
            published_at=snippet.get("publishedAt", ""),
        )
        unfiltered_results.append(video)
        if min_duration_seconds <= duration <= max_duration_seconds:
            filtered_results.append(video)

    # Fallback: jika filter durasi terlalu ketat, tetap kembalikan data trending.
    if filtered_results:
        return filtered_results
    return unfiltered_results


def _parse_published_at(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _score_video(views: int, likes: int, comments: int, published_at: str) -> float:
    now = datetime.now(timezone.utc)
    published = _parse_published_at(published_at)
    hours_since = max(1.0, (now - published).total_seconds() / 3600.0)
    engagement = likes * 2 + comments * 3
    return (views + engagement) / ((hours_since + 2.0) ** 0.65)


def fetch_top_viewed_recent_videos(
    api_key: str,
    days_back: int = 3,
    max_results: int = 10,
    min_duration_seconds: int = 60,
    max_duration_seconds: int = 2400,
) -> List[TrendingVideo]:
    days_back = max(1, min(7, days_back))
    youtube = build("youtube", "v3", developerKey=api_key)

    published_after = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
    candidate_limit = max(25, min(50, max_results * 4))

    search_response = (
        youtube.search()
        .list(
            part="id",
            type="video",
            order="viewCount",
            publishedAfter=published_after,
            maxResults=candidate_limit,
        )
        .execute()
    )

    ids = [item.get("id", {}).get("videoId", "") for item in search_response.get("items", [])]
    ids = [video_id for video_id in ids if video_id]
    if not ids:
        return []

    details_response = (
        youtube.videos()
        .list(
            part="snippet,statistics,contentDetails",
            id=",".join(ids[:50]),
            maxResults=50,
        )
        .execute()
    )

    filtered_results: List[TrendingVideo] = []
    unfiltered_results: List[TrendingVideo] = []

    for item in details_response.get("items", []):
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})
        duration = parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
        views = int(stats.get("viewCount", 0))
        likes = int(stats.get("likeCount", 0))
        comments = int(stats.get("commentCount", 0))
        published_at = snippet.get("publishedAt", "")

        video = TrendingVideo(
            video_id=item.get("id", ""),
            title=snippet.get("title", ""),
            channel=snippet.get("channelTitle", ""),
            views=views,
            duration_seconds=duration,
            published_at=published_at,
            score=_score_video(views, likes, comments, published_at),
        )

        unfiltered_results.append(video)
        if min_duration_seconds <= duration <= max_duration_seconds:
            filtered_results.append(video)

    target = filtered_results if filtered_results else unfiltered_results
    target.sort(key=lambda v: (v.score, v.views), reverse=True)
    return target[:max_results]
