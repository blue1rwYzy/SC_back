"""
知识图谱服务
负责：
1. 从专家知识与检测结果生成图谱
2. 将图谱写入 Neo4j
3. 提供图谱查询、推荐与自然语言问答能力
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from sqlalchemy.orm import Session

from config.neo4j_config import (
    NEO4J_PASSWORD,
    NEO4J_TIMEOUT,
    NEO4J_USERNAME,
    get_neo4j_tx_commit_url,
)
from shared import InferenceResult


SEVERITY_ONTOLOGY: Dict[int, Dict[str, str]] = {
    1: {
        "name": "轻微",
        "priority": "低",
        "timeline": "纳入日常巡检观察周期",
        "action": "保持监测并安排例行封缝或表面养护",
    },
    2: {
        "name": "较轻",
        "priority": "较低",
        "timeline": "1-3个月内完成处治",
        "action": "进行局部封缝、灌缝或表面修补，防止继续扩展",
    },
    3: {
        "name": "中等",
        "priority": "中",
        "timeline": "尽快安排专项养护",
        "action": "开展局部挖补、裂缝修补或基层病害复核",
    },
    4: {
        "name": "严重",
        "priority": "高",
        "timeline": "1个月内完成处治",
        "action": "优先安排应急养护，结合病害成因进行结构性补强",
    },
    5: {
        "name": "极严重",
        "priority": "最高",
        "timeline": "立即处置",
        "action": "启动应急响应，必要时实施交通管制并尽快完成重修",
    },
}


DEFECT_ONTOLOGY: Dict[str, Dict[str, Any]] = {
    "CrackFamily": {
        "display_name": "裂缝类病害",
        "node_label": "DefectFamily",
        "aliases": ["裂缝", "路面裂缝", "裂缝病害"],
        "description": "道路表面出现线状或网状开裂的病害集合。",
        "causes": ["温度收缩", "疲劳荷载作用", "基层承载力不足", "水损害"],
        "measures": ["裂缝封缝", "灌缝养护", "局部补强", "排水整治"],
        "standards": ["公路沥青路面养护技术规范", "公路技术状况评定标准"],
        "devices": ["车载摄像头", "固定监控设备", "无人机巡检设备"],
    },
    "Alligator_crack": {
        "display_name": "龟裂",
        "node_label": "DefectType",
        "aliases": ["龟裂", "网裂", "鳄鱼裂缝", "alligator crack"],
        "description": "路面形成网状裂缝，多与结构疲劳和承载不足有关。",
        "parent": "CrackFamily",
        "causes": ["疲劳荷载作用", "基层承载力不足", "长期水损害"],
        "measures": ["铣刨重铺", "基层补强", "排水整治"],
        "standards": ["公路沥青路面养护技术规范", "公路技术状况评定标准"],
        "devices": ["车载摄像头", "无人机巡检设备"],
    },
    "Longitudinal_crack": {
        "display_name": "纵向裂缝",
        "node_label": "DefectType",
        "aliases": ["纵向裂缝", "纵裂", "longitudinal crack"],
        "description": "沿道路行车方向延伸的裂缝，常与不均匀沉降和施工接缝有关。",
        "parent": "CrackFamily",
        "causes": ["不均匀沉降", "施工接缝质量不足", "反射裂缝"],
        "measures": ["灌缝封缝", "局部补强", "基层处治"],
        "standards": ["公路沥青路面养护技术规范", "公路技术状况评定标准"],
        "devices": ["车载摄像头", "固定监控设备"],
    },
    "Oblique_crack": {
        "display_name": "斜向裂缝",
        "node_label": "DefectType",
        "aliases": ["斜向裂缝", "斜裂", "oblique crack"],
        "description": "以斜向形式出现在路面的裂缝，通常受剪切力和局部变形影响。",
        "parent": "CrackFamily",
        "causes": ["剪切应力集中", "车辆偏载", "路基局部变形"],
        "measures": ["裂缝封补", "局部挖补", "交通荷载复核"],
        "standards": ["公路沥青路面养护技术规范"],
        "devices": ["车载摄像头", "无人机巡检设备"],
    },
    "Transverse_crack": {
        "display_name": "横向裂缝",
        "node_label": "DefectType",
        "aliases": ["横向裂缝", "横裂", "transverse crack"],
        "description": "横跨路面的裂缝，多与温缩或材料老化有关。",
        "parent": "CrackFamily",
        "causes": ["温度收缩", "材料老化", "接缝处理不当"],
        "measures": ["灌缝", "封层养护", "局部罩面"],
        "standards": ["公路沥青路面养护技术规范"],
        "devices": ["车载摄像头", "固定监控设备"],
    },
    "Pothole": {
        "display_name": "坑洞",
        "node_label": "DefectType",
        "aliases": ["坑洞", "坑槽", "pothole"],
        "description": "路面材料脱落形成的坑槽，影响行车安全和舒适性。",
        "causes": ["表层松散", "雨水侵蚀", "裂缝未及时处治"],
        "measures": ["坑槽修补", "局部挖补", "排水修复"],
        "standards": ["公路沥青路面养护技术规范", "公路养护安全作业规程"],
        "devices": ["车载摄像头", "无人机巡检设备"],
    },
    "Repair": {
        "display_name": "修补区域",
        "node_label": "DefectType",
        "aliases": ["修补区域", "修补痕迹", "repair"],
        "description": "已实施养护处治的区域，可用于评估修补质量和复发风险。",
        "causes": ["历史病害处治", "重复养护区域", "修补材料老化"],
        "measures": ["复核修补质量", "定期复检", "必要时重新处治"],
        "standards": ["公路养护安全作业规程", "公路技术状况评定标准"],
        "devices": ["车载摄像头", "固定监控设备"],
    },
}


ENTITY_LABEL_TO_TEXT = {
    "DefectType": "缺陷类型",
    "DefectFamily": "缺陷家族",
    "Cause": "成因",
    "Maintenance": "养护措施",
    "RoadSection": "路段",
    "Device": "设备",
    "Standard": "规范",
    "Severity": "严重程度",
    "DetectionBatch": "检测批次",
    "GraphMeta": "图谱元数据",
}


QUESTION_HINTS = [
    "支持查询示例：裂缝的常见成因有哪些？",
    "支持查询示例：坑洞推荐采取什么养护措施？",
    "支持查询示例：横向裂缝常参考哪些规范？",
    "支持查询示例：龟裂主要集中在哪些路段？",
]


class Neo4jHTTPClient:
    """通过 HTTP API 访问 Neo4j"""

    def __init__(self):
        self.tx_commit_url = get_neo4j_tx_commit_url()
        self.auth = (NEO4J_USERNAME, NEO4J_PASSWORD)
        self.timeout = NEO4J_TIMEOUT

    def run_query(
        self,
        statement: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        payload = {
            "statements": [
                {
                    "statement": statement,
                    "parameters": parameters or {},
                }
            ]
        }
        response = requests.post(
            self.tx_commit_url,
            auth=self.auth,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        errors = data.get("errors") or []
        if errors:
            raise RuntimeError(errors[0].get("message", "Neo4j 查询失败"))

        results = data.get("results") or []
        if not results:
            return []

        columns = results[0].get("columns", [])
        rows: List[Dict[str, Any]] = []
        for item in results[0].get("data", []):
            row_values = item.get("row", [])
            rows.append(dict(zip(columns, row_values)))
        return rows

    def run_scalar(
        self,
        statement: str,
        parameters: Optional[Dict[str, Any]] = None,
        default: Any = None,
    ) -> Any:
        rows = self.run_query(statement, parameters)
        if not rows:
            return default
        first_row = rows[0]
        if not first_row:
            return default
        return list(first_row.values())[0]

    def ping(self) -> bool:
        try:
            return self.run_scalar("RETURN 1 AS ok", default=0) == 1
        except Exception:
            return False


class KnowledgeGraphService:
    """知识图谱业务服务"""

    MANAGED_LABEL = "HighwayInspectionKnowledgeGraph"
    PROJECT_KEY = "highway_abnormal_inspection_platform"

    def __init__(self):
        self.client = Neo4jHTTPClient()

    @staticmethod
    def _node_key(prefix: str, value: str) -> str:
        normalized = (
            value.strip()
            .replace(" ", "_")
            .replace("/", "_")
            .replace("\\", "_")
            .replace("-", "_")
        )
        return f"{prefix}:{normalized}"

    def _ensure_available(self):
        if not self.client.ping():
            raise RuntimeError("Neo4j 服务不可用，请检查图数据库运行状态")

    def _resolve_defect_key(self, defect_name: Optional[str]) -> Optional[str]:
        if not defect_name:
            return None
        candidate = defect_name.strip().lower()
        for key, info in DEFECT_ONTOLOGY.items():
            if key.lower() == candidate:
                return key
            aliases = info.get("aliases", [])
            for alias in aliases:
                if alias.lower() == candidate:
                    return key
        if "裂缝" in defect_name:
            return "CrackFamily"
        return None

    def _resolve_severity_level(self, raw_value: Any) -> Optional[int]:
        if raw_value is None:
            return None
        if isinstance(raw_value, int):
            return raw_value if raw_value in SEVERITY_ONTOLOGY else None
        text = str(raw_value).strip()
        if text.isdigit():
            value = int(text)
            return value if value in SEVERITY_ONTOLOGY else None

        for level, item in SEVERITY_ONTOLOGY.items():
            if item["name"] in text:
                return level
        return None

    def _derive_road_section(self, result: InferenceResult) -> str:
        relative_path = result.original_image_rel or ""
        parts = [part for part in relative_path.split("/") if part]

        # 典型格式: images/test3/xxx.jpg -> 路段标识取 test3
        if len(parts) >= 2 and parts[0] == "images":
            return parts[1]
        if parts:
            return parts[0]
        return result.batch_name or "default-section"

    def _collect_graph_source_data(self, db: Session) -> Dict[str, Any]:
        results = db.query(InferenceResult).all()

        section_defect_stats: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(
            lambda: defaultdict(
                lambda: {
                    "avg_confidence_sum": 0.0,
                    "count": 0,
                    "last_detected_at": None,
                    "severity_score_sum": 0.0,
                }
            )
        )
        batch_section_stats: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        defect_totals: Counter[str] = Counter()
        defect_severity_totals: Counter[Tuple[str, int]] = Counter()

        for result in results:
            section_name = self._derive_road_section(result)
            batch_name = result.batch_name or "default-batch"
            batch_section_stats[batch_name][section_name] += 1

            detections = result.detections or []
            if not isinstance(detections, list):
                continue

            for detection in detections:
                if not isinstance(detection, dict):
                    continue

                raw_defect_name = detection.get("class") or detection.get("defect_type")
                defect_key = self._resolve_defect_key(raw_defect_name)
                if not defect_key:
                    continue

                section_stats = section_defect_stats[section_name][defect_key]
                section_stats["count"] += 1
                section_stats["avg_confidence_sum"] += float(
                    detection.get("confidence") or 0
                )
                section_stats["severity_score_sum"] += float(
                    result.severity_score or 0
                )
                if (
                    result.created_at
                    and (
                        section_stats["last_detected_at"] is None
                        or result.created_at > section_stats["last_detected_at"]
                    )
                ):
                    section_stats["last_detected_at"] = result.created_at

                defect_totals[defect_key] += 1
                if result.severity_level:
                    defect_severity_totals[(defect_key, int(result.severity_level))] += 1

        return {
            "batch_section_stats": batch_section_stats,
            "defect_severity_totals": defect_severity_totals,
            "defect_totals": defect_totals,
            "inference_result_count": len(results),
            "section_defect_stats": section_defect_stats,
        }

    def _create_constraints(self):
        self.client.run_query(
            f"""
            CREATE CONSTRAINT knowledge_graph_unique_key IF NOT EXISTS
            FOR (n:{self.MANAGED_LABEL})
            REQUIRE n.kg_key IS UNIQUE
            """
        )

    def _clear_managed_graph(self):
        self.client.run_query(
            f"MATCH (n:{self.MANAGED_LABEL}) DETACH DELETE n"
        )

    def _merge_node(
        self,
        labels: List[str],
        kg_key: str,
        properties: Dict[str, Any],
    ):
        label_text = ":".join([self.MANAGED_LABEL] + labels)
        node_properties = {"project_key": self.PROJECT_KEY, **properties}
        self.client.run_query(
            f"""
            MERGE (n:{label_text} {{ kg_key: $kg_key }})
            SET n += $properties
            """,
            {"kg_key": kg_key, "properties": node_properties},
        )

    def _merge_relation(
        self,
        source_key: str,
        relation_type: str,
        target_key: str,
        properties: Optional[Dict[str, Any]] = None,
    ):
        relation_type = relation_type.strip().upper()
        self.client.run_query(
            f"""
            MATCH (a:{self.MANAGED_LABEL} {{ kg_key: $source_key }})
            MATCH (b:{self.MANAGED_LABEL} {{ kg_key: $target_key }})
            MERGE (a)-[r:{relation_type}]->(b)
            SET r += $properties
            """,
            {
                "source_key": source_key,
                "target_key": target_key,
                "properties": properties or {},
            },
        )

    def _seed_static_ontology(self):
        # 严重程度节点
        for level, item in SEVERITY_ONTOLOGY.items():
            severity_key = self._node_key("severity", str(level))
            self._merge_node(
                ["Severity"],
                severity_key,
                {
                    "category": ENTITY_LABEL_TO_TEXT["Severity"],
                    "display_type": "Severity",
                    "level": level,
                    "name": item["name"],
                    "priority": item["priority"],
                    "timeline": item["timeline"],
                    "action": item["action"],
                },
            )

        # 缺陷本体及相关知识
        for defect_code, defect_info in DEFECT_ONTOLOGY.items():
            node_label = defect_info.get("node_label", "DefectType")
            defect_key = self._node_key("defect", defect_code)
            self._merge_node(
                [node_label],
                defect_key,
                {
                    "aliases": defect_info.get("aliases", []),
                    "category": ENTITY_LABEL_TO_TEXT.get(node_label, "知识实体"),
                    "code": defect_code,
                    "description": defect_info.get("description", ""),
                    "display_type": node_label,
                    "name": defect_info["display_name"],
                },
            )

            parent = defect_info.get("parent")
            if parent:
                parent_key = self._node_key("defect", parent)
                self._merge_relation(defect_key, "BELONGS_TO", parent_key)

            for cause in defect_info.get("causes", []):
                cause_key = self._node_key("cause", cause)
                self._merge_node(
                    ["Cause"],
                    cause_key,
                    {
                        "category": ENTITY_LABEL_TO_TEXT["Cause"],
                        "display_type": "Cause",
                        "name": cause,
                    },
                )
                self._merge_relation(defect_key, "CAUSED_BY", cause_key)

            for maintenance in defect_info.get("measures", []):
                maintenance_key = self._node_key("maintenance", maintenance)
                self._merge_node(
                    ["Maintenance"],
                    maintenance_key,
                    {
                        "category": ENTITY_LABEL_TO_TEXT["Maintenance"],
                        "display_type": "Maintenance",
                        "name": maintenance,
                    },
                )
                self._merge_relation(defect_key, "TREATED_BY", maintenance_key)

            for standard in defect_info.get("standards", []):
                standard_key = self._node_key("standard", standard)
                self._merge_node(
                    ["Standard"],
                    standard_key,
                    {
                        "category": ENTITY_LABEL_TO_TEXT["Standard"],
                        "display_type": "Standard",
                        "name": standard,
                    },
                )
                self._merge_relation(defect_key, "REFERENCES", standard_key)

            for device in defect_info.get("devices", []):
                device_key = self._node_key("device", device)
                self._merge_node(
                    ["Device"],
                    device_key,
                    {
                        "category": ENTITY_LABEL_TO_TEXT["Device"],
                        "display_type": "Device",
                        "name": device,
                    },
                )
                self._merge_relation(defect_key, "DETECTED_BY", device_key)

            for level, item in SEVERITY_ONTOLOGY.items():
                severity_key = self._node_key("severity", str(level))
                self._merge_relation(
                    defect_key,
                    "REQUIRES_RESPONSE",
                    severity_key,
                    {
                        "action": item["action"],
                        "priority": item["priority"],
                        "timeline": item["timeline"],
                    },
                )

    def _sync_dynamic_result_knowledge(self, db: Session):
        source_data = self._collect_graph_source_data(db)

        for batch_name, sections in source_data["batch_section_stats"].items():
            batch_key = self._node_key("batch", batch_name)
            self._merge_node(
                ["DetectionBatch"],
                batch_key,
                {
                    "category": ENTITY_LABEL_TO_TEXT["DetectionBatch"],
                    "display_type": "DetectionBatch",
                    "name": batch_name,
                    "section_count": len(sections),
                },
            )

            for section_name, section_count in sections.items():
                section_key = self._node_key("section", section_name)
                self._merge_node(
                    ["RoadSection"],
                    section_key,
                    {
                        "category": ENTITY_LABEL_TO_TEXT["RoadSection"],
                        "display_type": "RoadSection",
                        "name": section_name,
                        "observation_count": section_count,
                    },
                )
                self._merge_relation(
                    batch_key,
                    "COVERS_SECTION",
                    section_key,
                    {"count": section_count},
                )

        for section_name, defect_map in source_data["section_defect_stats"].items():
            section_key = self._node_key("section", section_name)
            for defect_code, stats in defect_map.items():
                defect_key = self._node_key("defect", defect_code)
                avg_confidence = (
                    stats["avg_confidence_sum"] / stats["count"]
                    if stats["count"]
                    else 0
                )
                avg_severity = (
                    stats["severity_score_sum"] / stats["count"]
                    if stats["count"]
                    else 0
                )
                self._merge_relation(
                    section_key,
                    "HAS_DEFECT",
                    defect_key,
                    {
                        "avg_confidence": round(avg_confidence, 4),
                        "avg_severity_score": round(avg_severity, 4),
                        "count": stats["count"],
                        "last_detected_at": (
                            stats["last_detected_at"].isoformat()
                            if stats["last_detected_at"]
                            else ""
                        ),
                    },
                )

        for defect_code, total_count in source_data["defect_totals"].items():
            defect_key = self._node_key("defect", defect_code)
            self.client.run_query(
                f"""
                MATCH (n:{self.MANAGED_LABEL} {{ kg_key: $kg_key }})
                SET n.total_count = $total_count
                """,
                {"kg_key": defect_key, "total_count": total_count},
            )

        for (defect_code, severity_level), total_count in source_data[
            "defect_severity_totals"
        ].items():
            defect_key = self._node_key("defect", defect_code)
            severity_key = self._node_key("severity", str(severity_level))
            self._merge_relation(
                defect_key,
                "OBSERVED_AS",
                severity_key,
                {"count": total_count},
            )

        self._merge_node(
            ["GraphMeta"],
            "meta:knowledge-graph",
            {
                "category": ENTITY_LABEL_TO_TEXT["GraphMeta"],
                "display_type": "GraphMeta",
                "hint_examples": QUESTION_HINTS,
                "inference_result_count": source_data["inference_result_count"],
                "last_generated_at": datetime.now().isoformat(),
                "name": "知识图谱生成元数据",
            },
        )

        return source_data

    def ensure_graph(self, db: Session):
        self._ensure_available()
        total_nodes = self.client.run_scalar(
            f"MATCH (n:{self.MANAGED_LABEL}) RETURN count(n) AS total",
            default=0,
        )
        if not total_nodes:
            self.generate_graph(db, force_rebuild=True)

    def generate_graph(
        self,
        db: Session,
        force_rebuild: bool = True,
    ) -> Dict[str, Any]:
        self._ensure_available()
        self._create_constraints()
        if force_rebuild:
            self._clear_managed_graph()

        self._seed_static_ontology()
        source_data = self._sync_dynamic_result_knowledge(db)

        entity_counts = {}
        for label in ENTITY_LABEL_TO_TEXT:
            entity_counts[label] = self.client.run_scalar(
                f"""
                MATCH (n:{self.MANAGED_LABEL}:{label})
                RETURN count(n) AS total
                """,
                default=0,
            )

        relation_rows = self.client.run_query(
            f"""
            MATCH (a:{self.MANAGED_LABEL})-[r]->(b:{self.MANAGED_LABEL})
            RETURN type(r) AS relation_type, count(r) AS relation_count
            ORDER BY relation_count DESC, relation_type
            """
        )

        return {
            "entityCounts": entity_counts,
            "inferenceResultCount": source_data["inference_result_count"],
            "relationCounts": relation_rows,
            "success": True,
        }

    def get_overview(self, db: Session) -> Dict[str, Any]:
        self.ensure_graph(db)

        entity_counts = {}
        for label, label_name in ENTITY_LABEL_TO_TEXT.items():
            entity_counts[label] = {
                "count": self.client.run_scalar(
                    f"""
                    MATCH (n:{self.MANAGED_LABEL}:{label})
                    RETURN count(n) AS total
                    """,
                    default=0,
                ),
                "label": label_name,
            }

        top_defects = self.client.run_query(
            f"""
            MATCH (:{self.MANAGED_LABEL}:RoadSection)-[r:HAS_DEFECT]->(d:{self.MANAGED_LABEL}:DefectType)
            RETURN d.name AS name, sum(coalesce(r.count, 0)) AS count
            ORDER BY count DESC, name
            LIMIT 8
            """
        )

        relation_counts = self.client.run_query(
            f"""
            MATCH (a:{self.MANAGED_LABEL})-[r]->(b:{self.MANAGED_LABEL})
            RETURN type(r) AS relation_type, count(r) AS relation_count
            ORDER BY relation_count DESC, relation_type
            """
        )

        meta = self.client.run_query(
            f"""
            MATCH (n:{self.MANAGED_LABEL}:GraphMeta {{ kg_key: 'meta:knowledge-graph' }})
            RETURN properties(n) AS meta
            """
        )

        return {
            "entityCounts": entity_counts,
            "hintExamples": meta[0]["meta"].get("hint_examples", QUESTION_HINTS)
            if meta
            else QUESTION_HINTS,
            "inferenceResultCount": meta[0]["meta"].get("inference_result_count", 0)
            if meta
            else 0,
            "lastGeneratedAt": meta[0]["meta"].get("last_generated_at")
            if meta
            else None,
            "relationCounts": relation_counts,
            "topDefects": top_defects,
        }

    def _query_nodes(
        self,
        keyword: str = "",
        entity_type: str = "",
        defect_type: str = "",
        section_name: str = "",
        limit: int = 80,
    ) -> List[Dict[str, Any]]:
        keyword = keyword.strip().lower()
        defect_key = self._resolve_defect_key(defect_type)
        section_name = section_name.strip()

        cypher = f"""
        MATCH (n:{self.MANAGED_LABEL})
        WHERE (
            $keyword = '' OR
            toLower(coalesce(n.name, '')) CONTAINS $keyword OR
            any(alias IN coalesce(n.aliases, []) WHERE toLower(alias) CONTAINS $keyword)
        )
        AND ($entity_type = '' OR $entity_type IN labels(n))
        AND (
            $defect_key = '' OR
            n.kg_key = $defect_key OR
            (n:DefectType AND EXISTS {{
                MATCH (n)-[:BELONGS_TO]->(:{self.MANAGED_LABEL} {{ kg_key: $defect_key }})
            }})
        )
        AND ($section_name = '' OR (n:RoadSection AND n.name = $section_name))
        RETURN n.kg_key AS key, n.name AS name, labels(n) AS labels, properties(n) AS properties
        ORDER BY
            CASE
                WHEN 'DefectType' IN labels(n) THEN 0
                WHEN 'RoadSection' IN labels(n) THEN 1
                WHEN 'Maintenance' IN labels(n) THEN 2
                ELSE 3
            END,
            n.name
        LIMIT $limit
        """
        return self.client.run_query(
            cypher,
            {
                "defect_key": self._node_key("defect", defect_key)
                if defect_key
                else "",
                "entity_type": entity_type.strip(),
                "keyword": keyword,
                "limit": max(20, min(limit, 150)),
                "section_name": section_name,
            },
        )

    def _neighbor_nodes(self, keys: List[str]) -> List[Dict[str, Any]]:
        if not keys:
            return []
        return self.client.run_query(
            f"""
            MATCH (n:{self.MANAGED_LABEL})-[r]-(m:{self.MANAGED_LABEL})
            WHERE n.kg_key IN $keys
            RETURN DISTINCT m.kg_key AS key, m.name AS name, labels(m) AS labels, properties(m) AS properties
            LIMIT 60
            """,
            {"keys": keys},
        )

    def _graph_links(self, keys: List[str]) -> List[Dict[str, Any]]:
        if not keys:
            return []
        return self.client.run_query(
            f"""
            MATCH (a:{self.MANAGED_LABEL})-[r]->(b:{self.MANAGED_LABEL})
            WHERE a.kg_key IN $keys AND b.kg_key IN $keys
            RETURN
                a.kg_key AS source,
                b.kg_key AS target,
                type(r) AS relation_type,
                properties(r) AS properties
            ORDER BY relation_type
            """
            ,
            {"keys": keys},
        )

    def _symbol_size(self, labels: List[str], properties: Dict[str, Any]) -> int:
        if "DefectType" in labels:
            total_count = int(properties.get("total_count") or 0)
            return min(58, 34 + total_count)
        if "RoadSection" in labels:
            observation_count = int(properties.get("observation_count") or 0)
            return min(54, 30 + observation_count)
        if "Severity" in labels:
            return 28
        if "Maintenance" in labels:
            return 26
        if "Cause" in labels:
            return 24
        if "Standard" in labels:
            return 22
        if "Device" in labels:
            return 20
        if "DetectionBatch" in labels:
            return 22
        return 20

    def get_graph(
        self,
        db: Session,
        keyword: str = "",
        entity_type: str = "",
        defect_type: str = "",
        section_name: str = "",
        limit: int = 80,
    ) -> Dict[str, Any]:
        self.ensure_graph(db)

        primary_nodes = self._query_nodes(
            keyword=keyword,
            entity_type=entity_type,
            defect_type=defect_type,
            section_name=section_name,
            limit=limit,
        )
        keys = [node["key"] for node in primary_nodes]

        if keyword or entity_type or defect_type or section_name:
            for node in self._neighbor_nodes(keys):
                if node["key"] not in keys and len(keys) < limit:
                    primary_nodes.append(node)
                    keys.append(node["key"])

        links = self._graph_links(keys)

        categories = []
        seen_categories = set()
        nodes = []
        for node in primary_nodes:
            labels = node.get("labels", [])
            display_type = node["properties"].get("display_type")
            category_name = ENTITY_LABEL_TO_TEXT.get(display_type, "知识实体")
            if category_name not in seen_categories:
                seen_categories.add(category_name)
                categories.append({"name": category_name})

            nodes.append(
                {
                    "category": category_name,
                    "id": node["key"],
                    "labels": labels,
                    "name": node["name"],
                    "properties": node["properties"],
                    "symbolSize": self._symbol_size(labels, node["properties"]),
                }
            )

        graph_links = [
            {
                "name": link["relation_type"],
                "properties": link.get("properties", {}),
                "relationType": link["relation_type"],
                "source": link["source"],
                "target": link["target"],
                "value": link.get("properties", {}).get("count", 1),
            }
            for link in links
        ]

        return {
            "categories": categories,
            "links": graph_links,
            "nodes": nodes,
        }

    def search_entities(
        self,
        db: Session,
        keyword: str,
        entity_type: str = "",
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        self.ensure_graph(db)
        nodes = self._query_nodes(keyword=keyword, entity_type=entity_type, limit=limit)
        return [
            {
                "key": node["key"],
                "name": node["name"],
                "entityType": node["properties"].get("display_type"),
                "labels": node["labels"],
                "properties": node["properties"],
            }
            for node in nodes
        ]

    def _get_related_entities(
        self,
        source_key: str,
        relation_type: str,
        direction: str = "out",
    ) -> List[Dict[str, Any]]:
        relation_type = relation_type.upper()
        if direction == "out":
            statement = f"""
            MATCH (a:{self.MANAGED_LABEL} {{ kg_key: $source_key }})-[r:{relation_type}]->(b:{self.MANAGED_LABEL})
            RETURN b.kg_key AS key, b.name AS name, labels(b) AS labels, properties(b) AS properties, properties(r) AS relation
            ORDER BY b.name
            """
        else:
            statement = f"""
            MATCH (a:{self.MANAGED_LABEL})-[r:{relation_type}]->(b:{self.MANAGED_LABEL} {{ kg_key: $source_key }})
            RETURN a.kg_key AS key, a.name AS name, labels(a) AS labels, properties(a) AS properties, properties(r) AS relation
            ORDER BY a.name
            """

        return self.client.run_query(statement, {"source_key": source_key})

    def get_recommendation(
        self,
        db: Session,
        defect_type: str,
        severity_level: Optional[int] = None,
    ) -> Dict[str, Any]:
        self.ensure_graph(db)
        defect_code = self._resolve_defect_key(defect_type)
        if not defect_code:
            raise ValueError("未识别的缺陷类型")

        defect_key = self._node_key("defect", defect_code)
        defect_info = DEFECT_ONTOLOGY[defect_code]
        severity_level = severity_level or 3
        severity_level = self._resolve_severity_level(severity_level) or 3
        severity_info = SEVERITY_ONTOLOGY[severity_level]

        causes = self._get_related_entities(defect_key, "CAUSED_BY")
        measures = self._get_related_entities(defect_key, "TREATED_BY")
        standards = self._get_related_entities(defect_key, "REFERENCES")
        sections = self.client.run_query(
            f"""
            MATCH (s:{self.MANAGED_LABEL}:RoadSection)-[r:HAS_DEFECT]->(d:{self.MANAGED_LABEL} {{ kg_key: $defect_key }})
            RETURN s.name AS section_name, r.count AS count, r.avg_confidence AS avg_confidence, r.avg_severity_score AS avg_severity_score
            ORDER BY count DESC, section_name
            LIMIT 5
            """,
            {"defect_key": defect_key},
        )

        return {
            "defectType": defect_info["display_name"],
            "severity": {
                "level": severity_level,
                "name": severity_info["name"],
                "priority": severity_info["priority"],
                "timeline": severity_info["timeline"],
                "action": severity_info["action"],
            },
            "causes": [item["name"] for item in causes],
            "measures": [item["name"] for item in measures],
            "roadSections": sections,
            "standards": [item["name"] for item in standards],
            "summary": (
                f"针对{defect_info['display_name']}（{severity_info['name']}），"
                f"建议优先执行：{severity_info['action']}。"
            ),
        }

    def ask_question(self, db: Session, question: str) -> Dict[str, Any]:
        self.ensure_graph(db)
        question = question.strip()
        if not question:
            raise ValueError("问题不能为空")

        defect_code = None
        for key, info in DEFECT_ONTOLOGY.items():
            aliases = [key, info["display_name"], *info.get("aliases", [])]
            if any(alias in question for alias in aliases):
                defect_code = key
                break

        if defect_code is None and "裂缝" in question:
            defect_code = "CrackFamily"

        if defect_code is None:
            return {
                "answer": "暂未识别问题中的缺陷实体，请尝试使用如“裂缝、坑洞、龟裂、横向裂缝”等关键词重新提问。",
                "matchedDefect": None,
                "matchedIntent": "unknown",
                "relatedEntities": [],
                "suggestions": QUESTION_HINTS,
            }

        severity_level = self._resolve_severity_level(question)
        defect_info = DEFECT_ONTOLOGY[defect_code]
        defect_key = self._node_key("defect", defect_code)

        intent = "summary"
        answer = ""
        related_entities: List[Dict[str, Any]] = []

        if any(token in question for token in ["成因", "原因", "为什么"]):
            intent = "causes"
            causes = self._get_related_entities(defect_key, "CAUSED_BY")
            cause_names = [item["name"] for item in causes]
            related_entities = causes
            answer = (
                f"{defect_info['display_name']}的常见成因包括："
                f"{'、'.join(cause_names) if cause_names else '暂无图谱知识'}。"
            )
        elif any(token in question for token in ["措施", "养护", "修复", "处理", "处置", "建议"]):
            intent = "measures"
            recommendation = self.get_recommendation(
                db,
                defect_info["display_name"],
                severity_level=severity_level,
            )
            related_entities = [
                {"name": measure, "type": "Maintenance"} for measure in recommendation["measures"]
            ]
            answer = recommendation["summary"] + (
                f" 重点措施：{'、'.join(recommendation['measures']) or '暂无'}。"
            )
        elif any(token in question for token in ["规范", "标准", "依据"]):
            intent = "standards"
            standards = self._get_related_entities(defect_key, "REFERENCES")
            standard_names = [item["name"] for item in standards]
            related_entities = standards
            answer = (
                f"{defect_info['display_name']}可参考的规范包括："
                f"{'、'.join(standard_names) if standard_names else '暂无图谱知识'}。"
            )
        elif any(token in question for token in ["路段", "分布", "哪里", "位置"]):
            intent = "distribution"
            sections = self.client.run_query(
                f"""
                MATCH (s:{self.MANAGED_LABEL}:RoadSection)-[r:HAS_DEFECT]->(d:{self.MANAGED_LABEL} {{ kg_key: $defect_key }})
                RETURN s.name AS section_name, r.count AS count
                ORDER BY count DESC, section_name
                LIMIT 5
                """,
                {"defect_key": defect_key},
            )
            related_entities = [
                {
                    "name": item["section_name"],
                    "count": item["count"],
                    "type": "RoadSection",
                }
                for item in sections
            ]
            if sections:
                answer = (
                    f"{defect_info['display_name']}当前主要分布在："
                    + "；".join(
                        f"{item['section_name']}（{item['count']}次）" for item in sections
                    )
                    + "。"
                )
            else:
                answer = f"当前图谱中暂无 {defect_info['display_name']} 的路段分布数据。"
        else:
            causes = self._get_related_entities(defect_key, "CAUSED_BY")
            measures = self._get_related_entities(defect_key, "TREATED_BY")
            answer = (
                f"{defect_info['display_name']}：{defect_info.get('description', '')}"
                f" 常见成因包括{'、'.join(item['name'] for item in causes[:3]) or '暂无'}，"
                f"推荐措施包括{'、'.join(item['name'] for item in measures[:3]) or '暂无'}。"
            )
            related_entities = causes[:3] + measures[:3]

        return {
            "answer": answer,
            "matchedDefect": defect_info["display_name"],
            "matchedIntent": intent,
            "relatedEntities": related_entities,
            "suggestions": QUESTION_HINTS,
        }


knowledge_graph_service = KnowledgeGraphService()
