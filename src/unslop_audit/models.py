"""审计结果的数据模型。"""

from dataclasses import dataclass, field
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Dimension(str, Enum):
    SPACING = "1-Spacing"
    COLOR = "2-Color"
    ICONS = "3-Icons"
    COPY = "4-Copy"
    TYPE = "5-Type"
    LAYOUT = "6-Layout"
    DETAILS = "7-Details"
    VISUALS = "8-Visuals"
    MOTION = "9-Motion"


DIM_CN = {
    "1-Spacing": "间距",
    "2-Color": "颜色",
    "3-Icons": "图标",
    "4-Copy": "文案",
    "5-Type": "字体",
    "6-Layout": "布局",
    "7-Details": "细节",
    "8-Visuals": "视觉",
    "9-Motion": "动效",
}


@dataclass
class Finding:
    file: str
    line: int
    dimension: str
    severity: str
    pattern: str
    message: str
    suggestion: str = ""
    context: str = ""


@dataclass
class AuditReport:
    scanned_files: int = 0
    total_findings: int = 0
    by_dimension: dict = field(default_factory=dict)
    by_severity: dict = field(default_factory=dict)
    findings: list = field(default_factory=list)
    score: int = 100
