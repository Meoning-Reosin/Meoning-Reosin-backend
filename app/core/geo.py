"""거리와 도보 시간 계산 (여러 기능이 함께 씀: 관광지 목록, 코스, 일정).

지금은 두 좌표 사이의 직선거리로 어림한다. 실제 길은 직선보다 길어서 DETOUR_FACTOR를 곱한다.
정확한 도보 경로가 필요해지면 TMAP 보행자 경로 API로 바꾼다 (API 14번, 확장안).
"""

import math

EARTH_RADIUS_M = 6_371_000
WALK_METERS_PER_MINUTE = 67  # 시속 약 4km
DETOUR_FACTOR = 1.3  # 직선거리 × 1.3 ≈ 실제 걷는 거리 (어림값)


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    """두 좌표 사이의 직선거리(미터). 지구를 공으로 보고 계산하는 하버사인 공식."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)))


def walk_minutes(straight_distance_m: int) -> int:
    """직선거리로 어림한 도보 시간(분). 최소 1분."""
    return max(1, math.ceil(straight_distance_m * DETOUR_FACTOR / WALK_METERS_PER_MINUTE))
