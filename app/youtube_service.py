from __future__ import annotations

import re
from dataclasses import dataclass
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
    response = (
        youtube.videos()
        .list(
            part="snippet,statistics,contentDetails",
            chart="mostPopular",
            regionCode=region_code,
            videoCategoryId=category_id,
            maxResults=max_results,
        )
        .execute()
    )

    results: List[TrendingVideo] = []
    for item in response.get("items", []):
        duration = parse_iso8601_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
        if duration < min_duration_seconds or duration > max_duration_seconds:
            continue

        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        results.append(
            TrendingVideo(
                video_id=item.get("id", ""),
                title=snippet.get("title", ""),
                channel=snippet.get("channelTitle", ""),
                views=int(stats.get("viewCount", 0)),
                duration_seconds=duration,
                published_at=snippet.get("publishedAt", ""),
            )
        )
    return results
