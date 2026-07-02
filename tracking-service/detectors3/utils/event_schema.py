"""事件类型枚举与 JSON Schema 定义。"""
from enum import Enum


class EventType(str, Enum):
    SPEEDING = "speeding"
    HARD_BRAKE = "hard_brake"
    STATIONARY = "stationary"
    LANE_CHANGE = "lane_change"
    CONGESTION = "congestion"
    ILLEGAL_PARKING = "illegal_parking"
    WRONG_WAY = "wrong_way"
    UNKNOWN = "unknown"


# 旧事件类型 → 新枚举的映射
EVENT_TYPE_MAP = {
    "speeding": EventType.SPEEDING,
    "abrupt_stop": EventType.HARD_BRAKE,
    "stationary": EventType.STATIONARY,
    "lane_change": EventType.LANE_CHANGE,
    "congestion": EventType.CONGESTION,
}
