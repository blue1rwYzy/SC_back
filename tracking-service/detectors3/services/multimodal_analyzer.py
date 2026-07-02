"""
多模态交通场景理解引擎
======================

基于视觉大模型(VLM)的深度场景分析，超越简单的事件检测，实现：
1. 交通场景全面理解（标志、信号灯、道路状况）
2. 复杂场景识别（施工、事故、特殊事件）
3. 风险等级评估
4. 智能建议生成

这是系统的核心智能模块，展示AI的深度理解能力。
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from services.vlm_client import VLMClient
from utils.image_encode import image_to_base64


class SceneComplexity(str, Enum):
    """场景复杂度等级"""
    SIMPLE = "simple"           # 简单场景：正常交通流
    MODERATE = "moderate"       # 中等场景：轻微异常
    COMPLEX = "complex"         # 复杂场景：多车交互
    CRITICAL = "critical"       # 危急场景：事故/拥堵


class RiskLevel(str, Enum):
    """风险等级"""
    LOW = "low"                 # 低风险
    MEDIUM = "medium"           # 中等风险
    HIGH = "high"               # 高风险
    CRITICAL = "critical"       # 危急风险


@dataclass
class TrafficSign:
    """交通标志"""
    sign_type: str              # 标志类型（限速、禁止、指示等）
    content: str                # 标志内容
    confidence: float           # 置信度
    location: Tuple[int, int]   # 位置坐标


@dataclass
class TrafficLight:
    """交通信号灯"""
    state: str                  # 状态（红、黄、绿）
    confidence: float           # 置信度
    location: Tuple[int, int]   # 位置坐标


@dataclass
class RoadCondition:
    """道路状况"""
    surface: str                # 路面状况（干燥、湿滑、积水等）
    visibility: str             # 能见度（良好、一般、差）
    weather: str                # 天气状况
    obstacles: List[str]        # 障碍物


@dataclass
class SceneAnalysis:
    """场景分析结果"""
    scene_id: str
    frame_id: int
    complexity: SceneComplexity
    risk_level: RiskLevel
    
    # 场景元素
    traffic_signs: List[TrafficSign]
    traffic_lights: List[TrafficLight]
    road_condition: RoadCondition
    
    # 车辆分析
    vehicle_count: int
    vehicle_behaviors: List[Dict]
    
    # 场景描述
    scene_description: str
    risk_factors: List[str]
    recommendations: List[str]
    
    # 元数据
    confidence: float
    analysis_time: float


class MultimodalTrafficAnalyzer:
    """
    多模态交通场景分析器
    
    使用VLM对交通场景进行深度理解，超越简单的事件检测，
    实现场景级别的智能分析。
    """
    
    def __init__(self, provider: str = "aistudio"):
        """
        初始化分析器
        
        Args:
            provider: VLM服务提供商 ("aistudio" 或 "gemini")
        """
        self.vlm = VLMClient(provider)
        self.analysis_history = []
        
    def analyze_scene(
        self,
        frame_path: str,
        frame_id: int,
        detections: List[Dict],
        events: List[Dict]
    ) -> SceneAnalysis:
        """
        分析单帧交通场景
        
        Args:
            frame_path: 帧图像路径
            frame_id: 帧编号
            detections: 检测结果列表
            events: 事件列表
            
        Returns:
            SceneAnalysis: 场景分析结果
        """
        # 构建分析提示词
        prompt = self._build_analysis_prompt(detections, events)
        
        # 调用VLM进行分析
        image_b64 = image_to_base64(frame_path)
        
        try:
            response = self.vlm.client.chat.completions.create(
                model=self.vlm.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content
            analysis = self._parse_analysis_result(
                frame_id, result_text, detections, events
            )
            
            self.analysis_history.append(analysis)
            return analysis
            
        except Exception as e:
            print(f"[MultimodalAnalyzer] 分析失败: {e}")
            return self._create_fallback_analysis(frame_id, detections, events)
    
    def _build_analysis_prompt(
        self,
        detections: List[Dict],
        events: List[Dict]
    ) -> str:
        """构建分析提示词"""
        
        detection_summary = ""
        if detections:
            detection_summary = f"\n检测到 {len(detections)} 辆车："
            for i, det in enumerate(detections[:5]):  # 只显示前5个
                detection_summary += f"\n- 车辆{i+1}: {det.get('class_name', 'vehicle')}"
        
        event_summary = ""
        if events:
            event_summary = "\n检测到的事件："
            for event in events:
                event_summary += f"\n- {event.get('type', 'unknown')}: {event.get('description', '')}"
        
        prompt = f"""你是一个专业的交通场景分析专家。请对这张交通监控图像进行深度分析。

{detection_summary}
{event_summary}

请从以下维度进行分析：

## 1. 场景复杂度评估
- 简单：正常交通流，无异常
- 中等：轻微异常，如个别车辆行为异常
- 复杂：多车交互，交通状况复杂
- 危急：事故、严重拥堵、危险情况

## 2. 交通元素识别
### 交通标志
- 识别图像中的交通标志
- 标注标志类型和内容
- 评估标志的可见性

### 交通信号灯
- 识别信号灯状态（红/黄/绿）
- 评估信号灯的可见性
- 判断信号灯是否正常工作

### 道路状况
- 路面状况（干燥/湿滑/积水/损坏）
- 能见度（良好/一般/差）
- 天气影响
- 障碍物识别

## 3. 风险评估
- 识别潜在风险因素
- 评估风险等级（低/中/高/危急）
- 分析风险来源

## 4. 智能建议
- 基于分析结果给出建议
- 针对发现的问题提出解决方案
- 预防性建议

## 5. 场景描述
用2-3句话概括整个场景的状况。

请以JSON格式输出分析结果，包含以下字段：
```json
{{
    "complexity": "simple/moderate/complex/critical",
    "risk_level": "low/medium/high/critical",
    "traffic_signs": [
        {{
            "type": "限速/禁止/指示等",
            "content": "标志内容",
            "confidence": 0.95,
            "location": [x, y]
        }}
    ],
    "traffic_lights": [
        {{
            "state": "red/yellow/green",
            "confidence": 0.95,
            "location": [x, y]
        }}
    ],
    "road_condition": {{
        "surface": "干燥/湿滑/积水",
        "visibility": "良好/一般/差",
        "weather": "晴/阴/雨/雾",
        "obstacles": ["障碍物1", "障碍物2"]
    }},
    "vehicle_behaviors": [
        {{
            "vehicle_id": 1,
            "behavior": "正常行驶/异常行为描述",
            "risk": "低/中/高"
        }}
    ],
    "risk_factors": ["风险因素1", "风险因素2"],
    "recommendations": ["建议1", "建议2"],
    "scene_description": "场景描述",
    "confidence": 0.9
}}
```"""
        
        return prompt
    
    def _parse_analysis_result(
        self,
        frame_id: int,
        result_text: str,
        detections: List[Dict],
        events: List[Dict]
    ) -> SceneAnalysis:
        """解析VLM分析结果"""
        
        try:
            # 尝试从文本中提取JSON
            json_start = result_text.find('{')
            json_end = result_text.rfind('}') + 1
            
            if json_start != -1 and json_end > json_start:
                json_str = result_text[json_start:json_end]
                result = json.loads(json_str)
            else:
                # 如果没有JSON，使用默认值
                result = self._extract_info_from_text(result_text)
            
            # 解析交通标志
            traffic_signs = []
            for sign in result.get('traffic_signs', []):
                traffic_signs.append(TrafficSign(
                    sign_type=sign.get('type', '未知'),
                    content=sign.get('content', ''),
                    confidence=sign.get('confidence', 0.5),
                    location=tuple(sign.get('location', [0, 0]))
                ))
            
            # 解析交通信号灯
            traffic_lights = []
            for light in result.get('traffic_lights', []):
                traffic_lights.append(TrafficLight(
                    state=light.get('state', 'unknown'),
                    confidence=light.get('confidence', 0.5),
                    location=tuple(light.get('location', [0, 0]))
                ))
            
            # 解析道路状况
            road_data = result.get('road_condition', {})
            road_condition = RoadCondition(
                surface=road_data.get('surface', '未知'),
                visibility=road_data.get('visibility', '未知'),
                weather=road_data.get('weather', '未知'),
                obstacles=road_data.get('obstacles', [])
            )
            
            # 构建分析结果
            analysis = SceneAnalysis(
                scene_id=f"scene_{frame_id}",
                frame_id=frame_id,
                complexity=SceneComplexity(result.get('complexity', 'moderate')),
                risk_level=RiskLevel(result.get('risk_level', 'medium')),
                traffic_signs=traffic_signs,
                traffic_lights=traffic_lights,
                road_condition=road_condition,
                vehicle_count=len(detections),
                vehicle_behaviors=result.get('vehicle_behaviors', []),
                scene_description=result.get('scene_description', ''),
                risk_factors=result.get('risk_factors', []),
                recommendations=result.get('recommendations', []),
                confidence=result.get('confidence', 0.5),
                analysis_time=0.0
            )
            
            return analysis
            
        except Exception as e:
            print(f"[MultimodalAnalyzer] 解析结果失败: {e}")
            return self._create_fallback_analysis(frame_id, detections, events)
    
    def _extract_info_from_text(self, text: str) -> Dict:
        """从文本中提取信息（当没有JSON时）"""
        
        # 简单的文本解析逻辑
        result = {
            'complexity': 'moderate',
            'risk_level': 'medium',
            'traffic_signs': [],
            'traffic_lights': [],
            'road_condition': {
                'surface': '未知',
                'visibility': '未知',
                'weather': '未知',
                'obstacles': []
            },
            'vehicle_behaviors': [],
            'risk_factors': [],
            'recommendations': [],
            'scene_description': text[:200] if text else '',
            'confidence': 0.5
        }
        
        # 尝试从文本中提取关键信息
        text_lower = text.lower()
        
        # 检测复杂度
        if '危急' in text or 'critical' in text_lower:
            result['complexity'] = 'critical'
        elif '复杂' in text or 'complex' in text_lower:
            result['complexity'] = 'complex'
        elif '简单' in text or 'simple' in text_lower:
            result['complexity'] = 'simple'
        
        # 检测风险等级
        if '高风险' in text or 'high risk' in text_lower:
            result['risk_level'] = 'high'
        elif '低风险' in text or 'low risk' in text_lower:
            result['risk_level'] = 'low'
        elif '危急' in text or 'critical' in text_lower:
            result['risk_level'] = 'critical'
        
        return result
    
    def _create_fallback_analysis(
        self,
        frame_id: int,
        detections: List[Dict],
        events: List[Dict]
    ) -> SceneAnalysis:
        """创建备用分析结果（当VLM分析失败时）"""
        
        # 基于检测结果和事件进行简单分析
        vehicle_count = len(detections)
        event_count = len(events)
        
        # 简单的复杂度评估
        if event_count > 5:
            complexity = SceneComplexity.CRITICAL
            risk_level = RiskLevel.CRITICAL
        elif event_count > 2:
            complexity = SceneComplexity.COMPLEX
            risk_level = RiskLevel.HIGH
        elif event_count > 0:
            complexity = SceneComplexity.MODERATE
            risk_level = RiskLevel.MEDIUM
        else:
            complexity = SceneComplexity.SIMPLE
            risk_level = RiskLevel.LOW
        
        # 提取风险因素
        risk_factors = []
        for event in events:
            event_type = event.get('type', '')
            if event_type == 'speeding':
                risk_factors.append('超速行驶')
            elif event_type == 'abrupt_stop':
                risk_factors.append('急刹车')
            elif event_type == 'stationary':
                risk_factors.append('异常停车')
            elif event_type == 'lane_change':
                risk_factors.append('频繁变道')
            elif event_type == 'congestion':
                risk_factors.append('交通拥堵')
        
        # 生成建议
        recommendations = []
        if '超速行驶' in risk_factors:
            recommendations.append('建议加强速度监控')
        if '急刹车' in risk_factors:
            recommendations.append('注意保持安全车距')
        if '交通拥堵' in risk_factors:
            recommendations.append('建议疏导交通')
        if not recommendations:
            recommendations.append('继续保持良好交通秩序')
        
        return SceneAnalysis(
            scene_id=f"scene_{frame_id}",
            frame_id=frame_id,
            complexity=complexity,
            risk_level=risk_level,
            traffic_signs=[],
            traffic_lights=[],
            road_condition=RoadCondition(
                surface='未知',
                visibility='未知',
                weather='未知',
                obstacles=[]
            ),
            vehicle_count=vehicle_count,
            vehicle_behaviors=[],
            scene_description=f'检测到{vehicle_count}辆车，{event_count}个异常事件',
            risk_factors=risk_factors,
            recommendations=recommendations,
            confidence=0.3,
            analysis_time=0.0
        )
    
    def get_scene_summary(self) -> Dict:
        """获取场景分析汇总"""
        
        if not self.analysis_history:
            return {
                'total_scenes': 0,
                'average_complexity': 'unknown',
                'average_risk': 'unknown',
                'common_risk_factors': [],
                'recommendations': []
            }
        
        # 统计复杂度分布
        complexity_counts = {}
        risk_counts = {}
        all_risk_factors = []
        all_recommendations = []
        
        for analysis in self.analysis_history:
            # 复杂度统计
            complexity = analysis.complexity.value
            complexity_counts[complexity] = complexity_counts.get(complexity, 0) + 1
            
            # 风险等级统计
            risk = analysis.risk_level.value
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
            
            # 收集风险因素和建议
            all_risk_factors.extend(analysis.risk_factors)
            all_recommendations.extend(analysis.recommendations)
        
        # 计算最常见的风险因素
        risk_factor_counts = {}
        for factor in all_risk_factors:
            risk_factor_counts[factor] = risk_factor_counts.get(factor, 0) + 1
        common_risk_factors = sorted(
            risk_factor_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # 计算最常见的建议
        recommendation_counts = {}
        for rec in all_recommendations:
            recommendation_counts[rec] = recommendation_counts.get(rec, 0) + 1
        common_recommendations = sorted(
            recommendation_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # 计算平均复杂度和风险等级
        complexity_order = ['simple', 'moderate', 'complex', 'critical']
        risk_order = ['low', 'medium', 'high', 'critical']
        
        avg_complexity_idx = sum(
            complexity_order.index(c) * count
            for c, count in complexity_counts.items()
        ) / len(self.analysis_history)
        avg_complexity = complexity_order[min(3, int(avg_complexity_idx))]
        
        avg_risk_idx = sum(
            risk_order.index(r) * count
            for r, count in risk_counts.items()
        ) / len(self.analysis_history)
        avg_risk = risk_order[min(3, int(avg_risk_idx))]
        
        return {
            'total_scenes': len(self.analysis_history),
            'complexity_distribution': complexity_counts,
            'risk_distribution': risk_counts,
            'average_complexity': avg_complexity,
            'average_risk': avg_risk,
            'common_risk_factors': [f[0] for f in common_risk_factors],
            'common_recommendations': [r[0] for r in common_recommendations]
        }
    
    def generate_intelligent_report(self) -> str:
        """生成智能分析报告"""
        
        summary = self.get_scene_summary()
        
        if summary['total_scenes'] == 0:
            return "暂无场景分析数据"
        
        report = f"""# 智能交通场景分析报告

## 分析概览
- 分析场景总数：{summary['total_scenes']}
- 平均场景复杂度：{summary['average_complexity']}
- 平均风险等级：{summary['average_risk']}

## 复杂度分布
"""
        
        for complexity, count in summary.get('complexity_distribution', {}).items():
            percentage = count / summary['total_scenes'] * 100
            report += f"- {complexity}: {count} ({percentage:.1f}%)\n"
        
        report += "\n## 风险等级分布\n"
        for risk, count in summary.get('risk_distribution', {}).items():
            percentage = count / summary['total_scenes'] * 100
            report += f"- {risk}: {count} ({percentage:.1f}%)\n"
        
        report += "\n## 主要风险因素\n"
        for factor in summary.get('common_risk_factors', []):
            report += f"- {factor}\n"
        
        report += "\n## 智能建议\n"
        for recommendation in summary.get('common_recommendations', []):
            report += f"- {recommendation}\n"
        
        report += "\n## 场景分析详情\n"
        for i, analysis in enumerate(self.analysis_history[-10:], 1):  # 只显示最近10个
            report += f"""
### 场景 {i} (帧 {analysis.frame_id})
- 复杂度：{analysis.complexity.value}
- 风险等级：{analysis.risk_level.value}
- 车辆数量：{analysis.vehicle_count}
- 场景描述：{analysis.scene_description}
- 风险因素：{', '.join(analysis.risk_factors) if analysis.risk_factors else '无'}
- 建议：{', '.join(analysis.recommendations) if analysis.recommendations else '无'}
"""
        
        return report


# 便捷函数
def analyze_traffic_scene(
    frame_path: str,
    frame_id: int,
    detections: List[Dict],
    events: List[Dict],
    provider: str = "aistudio"
) -> SceneAnalysis:
    """
    便捷函数：分析交通场景
    
    Args:
        frame_path: 帧图像路径
        frame_id: 帧编号
        detections: 检测结果列表
        events: 事件列表
        provider: VLM服务提供商
        
    Returns:
        SceneAnalysis: 场景分析结果
    """
    analyzer = MultimodalTrafficAnalyzer(provider)
    return analyzer.analyze_scene(frame_path, frame_id, detections, events)
