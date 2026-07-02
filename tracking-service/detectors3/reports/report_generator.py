"""交通分析报告生成器：生成专业 HTML 报告 + LLM 智能分析。"""
import json
import os
from datetime import datetime

try:
    from services.llm_client import LLMClient
except Exception as exc:
    LLMClient = None
    LLM_IMPORT_ERROR = exc
else:
    LLM_IMPORT_ERROR = None


# ── SVG 图表工具 ──────────────────────────────────────────────

def _svg_bar_chart(counts: dict, width: int = 500, height: int = 220) -> str:
    """生成 SVG 水平柱状图。"""
    if not counts:
        return "<p class='empty'>暂无数据</p>"

    max_val = max(counts.values()) or 1
    bar_h = 32
    gap = 8
    label_w = 120
    chart_w = width - label_w - 60
    total_h = len(counts) * (bar_h + gap) + 20

    colors = {
        "speeding": "#ff4757", "abrupt_stop": "#ff6b81",
        "stationary": "#1e90ff", "lane_change": "#ffa502",
        "congestion": "#2ed573",
    }
    labels_cn = {
        "speeding": "超速", "abrupt_stop": "急刹车",
        "stationary": "静止", "lane_change": "变道",
        "congestion": "拥堵",
    }

    bars = ""
    y = 10
    for k, v in counts.items():
        color = colors.get(k, "#747d8c")
        label = labels_cn.get(k, k)
        bw = int((v / max_val) * chart_w) if max_val > 0 else 0
        bars += f'''
        <g>
          <text x="{label_w - 8}" y="{y + bar_h // 2 + 5}" text-anchor="end"
                fill="#a4b0be" font-size="13">{label}</text>
          <rect x="{label_w}" y="{y}" width="{bw}" height="{bar_h}"
                rx="4" fill="{color}" opacity="0.85">
            <animate attributeName="width" from="0" to="{bw}" dur="0.8s" fill="freeze"/>
          </rect>
          <text x="{label_w + bw + 8}" y="{y + bar_h // 2 + 5}"
                fill="#dfe6e9" font-size="13" font-weight="600">{v}</text>
        </g>'''
        y += bar_h + gap

    return f'''<svg width="{width}" height="{total_h}" xmlns="http://www.w3.org/2000/svg">
    {bars}</svg>'''


def _svg_speed_histogram(speeds: list, width: int = 500, height: int = 200) -> str:
    """生成 SVG 速度分布直方图。"""
    if not speeds:
        return "<p class='empty'>暂无速度数据</p>"

    bins = [0] * 12  # 0-10, 10-20, ..., 110-120
    for s in speeds:
        idx = min(int(s // 10), 11)
        bins[idx] += 1

    max_val = max(bins) or 1
    bar_w = (width - 80) // 12
    chart_h = height - 50

    bars = ""
    for i, count in enumerate(bins):
        bh = int((count / max_val) * chart_h) if max_val > 0 else 0
        x = 40 + i * bar_w
        y = chart_h - bh + 10
        ratio = i / 11
        if ratio < 0.5:
            color = f"rgb({int(40 + ratio * 2 * 180)}, {int(200 - ratio * 2 * 40)}, 60)"
        else:
            color = f"rgb(255, {int(160 - (ratio - 0.5) * 2 * 160)}, 60)"
        bars += f'''
        <rect x="{x + 2}" y="{y}" width="{bar_w - 4}" height="{bh}"
              rx="2" fill="{color}" opacity="0.8">
          <animate attributeName="height" from="0" to="{bh}" dur="0.6s" fill="freeze"/>
          <animate attributeName="y" from="{chart_h + 10}" to="{y}" dur="0.6s" fill="freeze"/>
        </rect>
        <text x="{x + bar_w // 2}" y="{chart_h + 24}" text-anchor="middle"
              fill="#a4b0be" font-size="10">{i * 10}</text>'''
        if count > 0:
            bars += f'''
        <text x="{x + bar_w // 2}" y="{y - 4}" text-anchor="middle"
              fill="#dfe6e9" font-size="10">{count}</text>'''

    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <text x="10" y="15" fill="#a4b0be" font-size="11">车辆数</text>
    <text x="{width // 2}" y="{height - 2}" text-anchor="middle"
          fill="#a4b0be" font-size="11">速度 (km/h)</text>
    {bars}</svg>'''


def _svg_speed_curve(audit_samples: list, fps: float, width: int = 600, height: int = 180) -> str:
    """生成 SVG 速度变化曲线。"""
    if len(audit_samples) < 2:
        return "<p class='empty'>样本不足</p>"

    points = [(s["frame"] / fps, s["speed_kmh"]) for s in audit_samples]
    max_s = max(s for _, s in points) * 1.2 or 120
    max_t = max(t for t, _ in points) or 1

    pad_l, pad_r, pad_t, pad_b = 50, 20, 20, 30
    cw = width - pad_l - pad_r
    ch = height - pad_t - pad_b

    def tx(t): return pad_l + int((t / max_t) * cw)
    def sy(s): return pad_t + ch - int((s / max_s) * ch)

    # 网格
    grid = ""
    for frac in [0.25, 0.5, 0.75]:
        yy = pad_t + int(ch * (1 - frac))
        val = int(max_s * frac)
        grid += f'''<line x1="{pad_l}" y1="{yy}" x2="{width - pad_r}" y2="{yy}"
                    stroke="#2d3436" stroke-width="1"/>
        <text x="{pad_l - 4}" y="{yy + 4}" text-anchor="end"
              fill="#636e72" font-size="10">{val}</text>'''

    # 曲线
    path_d = "M" + " L".join(f"{tx(t)},{sy(s)}" for t, s in points)
    area_d = path_d + f" L{tx(points[-1][0])},{pad_t + ch} L{tx(points[0][0])},{pad_t + ch} Z"

    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    {grid}
    <path d="{area_d}" fill="url(#grad)" opacity="0.3"/>
    <path d="{path_d}" fill="none" stroke="#0984e3" stroke-width="2"/>
    <defs><linearGradient id="grad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0984e3" stop-opacity="0.4"/>
      <stop offset="100%" stop-color="#0984e3" stop-opacity="0"/>
    </linearGradient></defs>
    <text x="{width // 2}" y="{height - 2}" text-anchor="middle"
          fill="#a4b0be" font-size="11">时间 (s) →</text>
    <text x="10" y="15" fill="#a4b0be" font-size="11">km/h</text>
    </svg>'''


def _svg_event_timeline(events: list, duration: float, width: int = 600, height: int = 80) -> str:
    """生成 SVG 事件时间轴。"""
    if not events:
        return "<p class='empty'>暂无事件</p>"

    colors = {
        "speeding": "#ff4757", "abrupt_stop": "#ff6b81",
        "stationary": "#1e90ff", "lane_change": "#ffa502",
        "congestion": "#2ed573",
    }
    labels_cn = {
        "speeding": "超速", "abrupt_stop": "急刹",
        "stationary": "静止", "lane_change": "变道",
        "congestion": "拥堵",
    }

    pad = 40
    tw = width - pad * 2
    bar_y = 30

    # 时间刻度
    ticks = ""
    for i in range(0, int(duration) + 1, max(1, int(duration / 10))):
        x = pad + int((i / max(duration, 1)) * tw)
        ticks += f'''<line x1="{x}" y1="{bar_y - 5}" x2="{x}" y2="{bar_y + 8}"
                      stroke="#636e72" stroke-width="1"/>
        <text x="{x}" y="{bar_y + 20}" text-anchor="middle"
              fill="#a4b0be" font-size="9">{i}s</text>'''

    # 事件点
    dots = ""
    for ev in events:
        t = ev.get("start_time", ev.get("time_s", 0))
        etype = ev.get("type", "unknown")
        color = colors.get(etype, "#747d8c")
        x = pad + int((t / max(duration, 1)) * tw)
        label = labels_cn.get(etype, etype[:3])
        dots += f'''
        <circle cx="{x}" cy="{bar_y}" r="6" fill="{color}" opacity="0.9">
          <title>[{t:.1f}s] {label}</title>
        </circle>'''

    return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
    <line x1="{pad}" y1="{bar_y}" x2="{width - pad}" y2="{bar_y}"
          stroke="#2d3436" stroke-width="3" stroke-linecap="round"/>
    {ticks}{dots}</svg>'''


# ── HTML 报告模板 ──────────────────────────────────────────────

def _build_html(
    data: dict,
    ai_analysis: str,
    responsibility_html: str,
    violation_html: str,
    risk_html: str,
) -> str:
    """根据 JSON 数据和 AI 分析，生成完整 HTML 报告。"""
    video = data.get("video_info", {})
    summary = data.get("summary", {})
    tracks = data.get("tracks", [])
    events = data.get("events", [])
    calibration = data.get("calibration", {})
    scene = data.get("scene_analysis", {})

    duration = video.get("duration_sec", 0)
    fps = video.get("fps", 30)
    resolution = video.get("resolution", [0, 0])
    vehicle_count = summary.get("vehicle_count", 0)
    event_count = summary.get("event_count", 0)
    breakdown = summary.get("event_breakdown", {})

    # 速度数据
    speeds = [t.get("avg_speed_kmh", 0) for t in tracks if t.get("avg_speed_kmh", 0) > 0]
    max_speeds = [t.get("max_speed_kmh", 0) for t in tracks if t.get("max_speed_kmh", 0) > 0]
    avg_speed = sum(speeds) / len(speeds) if speeds else 0
    max_speed = max(max_speeds) if max_speeds else 0

    # 事件详情表
    event_rows = ""
    for ev in events[:50]:
        etype = ev.get("type", "unknown")
        labels_cn = {
            "speeding": "超速", "abrupt_stop": "急刹车",
            "stationary": "静止", "lane_change": "变道",
            "congestion": "拥堵",
        }
        label = labels_cn.get(etype, etype)
        tid = ev.get("track_id", "-")
        t_start = ev.get("start_time", ev.get("time_s", 0))
        t_end = ev.get("end_time", "")
        conf = ev.get("confidence", 0)
        detail = ""
        if etype == "speeding":
            detail = f"速度 {ev.get('speed_kmh', '?')} km/h (限速 {ev.get('limit_kmh', '?')})"
        elif etype == "abrupt_stop":
            detail = f"减速度 {ev.get('decel_mps2', '?')} m/s²"
        elif etype == "congestion":
            detail = f"均速 {ev.get('avg_speed_kmh', '?')} km/h, {ev.get('n_vehicles', '?')} 辆"
        else:
            detail = ev.get("description", "")

        vlm = ev.get("vlm_check", {})
        vlm_str = ""
        if vlm and "raw_response" in vlm:
            raw = vlm["raw_response"]
            if isinstance(raw, str) and len(raw) > 80:
                raw = raw[:80] + "..."
            vlm_str = raw

        duration_str = f"{t_end - t_start:.1f}s" if isinstance(t_end, (int, float)) and t_end else "-"
        event_rows += f'''
        <tr>
          <td><span class="badge badge-{etype}">{label}</span></td>
          <td>#{tid}</td>
          <td>{t_start:.1f}s</td>
          <td>{duration_str}</td>
          <td>{detail}</td>
          <td>{conf:.0%}</td>
          <td class="vlm-cell">{vlm_str if vlm_str else '-'}</td>
        </tr>'''

    # 场景分析结果
    scene_html = ""
    if scene and scene.get("analyses"):
        scene_items = ""
        for a in scene["analyses"][:6]:
            scene_items += f'''
            <div class="scene-card">
              <div class="scene-header">
                <span class="scene-time">帧 {a.get('frame_id', '?')}</span>
                <span class="badge badge-{a.get('risk_level', 'low')}">{a.get('risk_level', '未知')}</span>
              </div>
              <p>{a.get('scene_description', '暂无描述')}</p>
              <div class="scene-meta">
                <span>复杂度: {a.get('complexity', '?')}</span>
                <span>车辆: {a.get('vehicle_count', '?')}</span>
              </div>
            </div>'''
        scene_html = f'''
        <section>
          <h2>场景复核</h2>
          <p class="section-desc">关键帧场景复核结果</p>
          <div class="scene-grid">{scene_items}</div>
        </section>'''

    # 车辆TOP速度表
    top_tracks = sorted(tracks, key=lambda t: t.get("max_speed_kmh", 0), reverse=True)[:10]
    top_rows = ""
    for t in top_tracks:
        top_rows += f'''
        <tr>
          <td>#{t.get('track_id', '?')}</td>
          <td>{t.get('avg_speed_kmh', 0):.1f}</td>
          <td>{t.get('max_speed_kmh', 0):.1f}</td>
          <td>{t.get('first_seen', 0):.1f}s</td>
          <td>{t.get('last_seen', 0):.1f}s</td>
          <td>{t.get('last_seen', 0) - t.get('first_seen', 0):.1f}s</td>
        </tr>'''

    # AI 分析 HTML
    ai_html = ""
    if ai_analysis:
        # 将 markdown 转换为简单 HTML
        ai_lines = ai_analysis.split("\n")
        ai_body = ""
        for line in ai_lines:
            line = line.strip()
            if not line:
                ai_body += "<br>"
            elif line.startswith("### "):
                ai_body += f"<h4>{line[4:]}</h4>"
            elif line.startswith("## "):
                ai_body += f"<h3>{line[3:]}</h3>"
            elif line.startswith("# "):
                ai_body += f"<h3>{line[2:]}</h3>"
            elif line.startswith("- ") or line.startswith("* "):
                ai_body += f"<li>{line[2:]}</li>"
            elif line.startswith("```"):
                continue
            else:
                ai_body += f"<p>{line}</p>"
        ai_html = f'''
        <section>
          <h2>辅助分析意见</h2>
          <div class="ai-analysis">{ai_body}</div>
        </section>'''

    # 校准信息
    scale_diag = calibration.get("scale_diag", {})
    ppm_median = scale_diag.get("ppm_median", 0)
    vp_diag = calibration.get("vp_diag", {})
    vp_count = vp_diag.get("n", 0)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>高速公路车辆追踪分析报告 - {video.get('video_name', '')}</title>
<style>
  :root {{
    --bg: #0f1923; --bg2: #162230; --bg3: #1a2d3e;
    --text: #dfe6e9; --text2: #a4b0be; --text3: #636e72;
    --accent: #0984e3; --accent2: #74b9ff;
    --red: #ff4757; --orange: #ffa502; --green: #2ed573; --blue: #1e90ff;
    --border: #2d3436; --shadow: rgba(0,0,0,0.3);
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
                 'Microsoft YaHei', sans-serif;
    background: var(--bg); color: var(--text);
    line-height: 1.6; padding: 0;
  }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 20px 24px; }}

  /* Header */
  .header {{
    background: linear-gradient(135deg, #0c1a2a 0%, #1a3050 50%, #0c2d4a 100%);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 32px 36px; margin-bottom: 24px;
    position: relative; overflow: hidden;
  }}
  .header::before {{
    content: ''; position: absolute; top: -50%; right: -20%;
    width: 400px; height: 400px; border-radius: 50%;
    background: radial-gradient(circle, rgba(9,132,227,0.08) 0%, transparent 70%);
  }}
  .header h1 {{
    font-size: 26px; font-weight: 700; color: #fff;
    margin-bottom: 6px; position: relative;
  }}
  .header h1 span {{ color: var(--accent2); }}
  .header .subtitle {{
    font-size: 14px; color: var(--text2); position: relative;
  }}
  .header .meta {{
    display: flex; gap: 24px; margin-top: 16px;
    font-size: 13px; color: var(--text3); position: relative;
  }}
  .header .meta span {{ display: flex; align-items: center; gap: 4px; }}

  /* Cards */
  .cards {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px; margin-bottom: 24px;
  }}
  .card {{
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 10px; padding: 20px; text-align: center;
    transition: transform 0.2s, border-color 0.2s;
  }}
  .card:hover {{ transform: translateY(-2px); border-color: var(--accent); }}
  .card .value {{
    font-size: 36px; font-weight: 700; color: var(--accent2);
    line-height: 1.2;
  }}
  .card .label {{ font-size: 13px; color: var(--text2); margin-top: 4px; }}
  .card.red .value {{ color: var(--red); }}
  .card.orange .value {{ color: var(--orange); }}
  .card.green .value {{ color: var(--green); }}

  /* Sections */
  section {{
    background: var(--bg2); border: 1px solid var(--border);
    border-radius: 10px; padding: 24px; margin-bottom: 20px;
  }}
  section h2 {{
    font-size: 18px; font-weight: 600; color: #fff;
    margin-bottom: 6px; padding-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }}
  .section-desc {{ font-size: 13px; color: var(--text3); margin-bottom: 16px; }}

  /* Charts */
  .chart-row {{
    display: grid; grid-template-columns: 1fr 1fr; gap: 20px;
    margin-bottom: 16px;
  }}
  .chart-box {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px;
  }}
  .chart-box h3 {{ font-size: 14px; color: var(--text2); margin-bottom: 12px; }}
  .chart-box svg {{ display: block; margin: 0 auto; }}

  /* Table */
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{
    background: var(--bg3); color: var(--text2); font-weight: 600;
    padding: 10px 12px; text-align: left; border-bottom: 2px solid var(--border);
  }}
  td {{
    padding: 8px 12px; border-bottom: 1px solid var(--border);
    color: var(--text);
  }}
  tr:hover td {{ background: rgba(9,132,227,0.05); }}
  .vlm-cell {{ font-size: 11px; color: var(--text3); max-width: 200px; }}

  /* Badges */
  .badge {{
    display: inline-block; padding: 2px 10px; border-radius: 12px;
    font-size: 12px; font-weight: 600;
  }}
  .badge-speeding {{ background: rgba(255,71,87,0.15); color: var(--red); }}
  .badge-abrupt_stop {{ background: rgba(255,107,129,0.15); color: #ff6b81; }}
  .badge-stationary {{ background: rgba(30,144,255,0.15); color: var(--blue); }}
  .badge-lane_change {{ background: rgba(255,165,2,0.15); color: var(--orange); }}
  .badge-congestion {{ background: rgba(46,213,115,0.15); color: var(--green); }}
  .badge-low {{ background: rgba(46,213,115,0.15); color: var(--green); }}
  .badge-medium {{ background: rgba(255,165,2,0.15); color: var(--orange); }}
  .badge-high {{ background: rgba(255,71,87,0.15); color: var(--red); }}
  .badge-critical {{ background: rgba(255,0,0,0.2); color: #ff0000; }}

  /* Scene cards */
  .scene-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
  }}
  .scene-card {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px;
  }}
  .scene-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 8px;
  }}
  .scene-time {{ font-size: 12px; color: var(--text3); }}
  .scene-card p {{ font-size: 13px; color: var(--text); margin-bottom: 8px; }}
  .scene-meta {{ font-size: 12px; color: var(--text3); display: flex; gap: 16px; }}

  /* AI Analysis */
  .ai-analysis {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 20px; font-size: 14px;
    line-height: 1.8;
  }}
  .ai-analysis h3 {{ color: var(--accent2); font-size: 16px; margin: 16px 0 8px; }}
  .ai-analysis h4 {{ color: var(--text); font-size: 14px; margin: 12px 0 6px; }}
  .ai-analysis li {{ margin-left: 20px; margin-bottom: 4px; }}
  .ai-analysis p {{ margin-bottom: 6px; }}

  /* Footer */
  .footer {{
    text-align: center; padding: 20px; font-size: 12px; color: var(--text3);
  }}

  /* Empty state */
  .empty {{ color: var(--text3); font-style: italic; text-align: center; padding: 20px; }}

  /* 责任判定模块 */
  .responsibility-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 16px;
  }}
  .responsibility-card {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; border-left: 4px solid var(--accent);
  }}
  .responsibility-card.high {{ border-left-color: var(--red); }}
  .responsibility-card.medium {{ border-left-color: var(--orange); }}
  .responsibility-card.low {{ border-left-color: var(--green); }}
  .responsibility-header {{
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 12px;
  }}
  .responsibility-title {{ font-weight: 600; color: #fff; }}
  .responsibility-time {{ font-size: 12px; color: var(--text3); }}
  .responsibility-body {{ font-size: 13px; color: var(--text); }}
  .responsibility-body .label {{ color: var(--text2); margin-bottom: 4px; }}
  .responsibility-body .content {{ margin-bottom: 8px; }}
  .responsibility-verdict {{
    background: var(--bg3); border-radius: 6px; padding: 10px;
    margin-top: 10px; font-size: 13px;
  }}
  .responsibility-verdict .verdict-label {{ color: var(--text2); }}
  .responsibility-verdict .verdict-text {{ color: #fff; font-weight: 500; }}

  /* 违法行为模块 */
  .violation-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 12px;
  }}
  .violation-card {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px; display: flex;
    align-items: flex-start; gap: 12px;
  }}
  .violation-icon {{
    width: 40px; height: 40px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0;
  }}
  .violation-icon.speeding {{ background: rgba(255,71,87,0.15); }}
  .violation-icon.braking {{ background: rgba(255,107,129,0.15); }}
  .violation-icon.lane {{ background: rgba(255,165,2,0.15); }}
  .violation-icon.stopped {{ background: rgba(30,144,255,0.15); }}
  .violation-content {{ flex: 1; }}
  .violation-title {{ font-weight: 600; color: #fff; margin-bottom: 4px; }}
  .violation-desc {{ font-size: 12px; color: var(--text2); margin-bottom: 6px; }}
  .violation-meta {{ font-size: 11px; color: var(--text3); }}
  .violation-meta .severity {{ font-weight: 600; }}
  .violation-meta .severity.high {{ color: var(--red); }}
  .violation-meta .severity.medium {{ color: var(--orange); }}
  .violation-meta .severity.low {{ color: var(--green); }}

  /* 风险评估模块 */
  .risk-assessment {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
  }}
  .risk-card {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; text-align: center;
  }}
  .risk-card .risk-icon {{
    font-size: 24px; margin-bottom: 8px;
  }}
  .risk-card .risk-title {{
    font-size: 13px; color: var(--text2); margin-bottom: 8px;
  }}
  .risk-card .risk-value {{
    font-size: 28px; font-weight: 700; margin-bottom: 4px;
  }}
  .risk-card .risk-level {{
    font-size: 12px; font-weight: 600; padding: 2px 10px;
    border-radius: 12px; display: inline-block;
  }}
  .risk-card .risk-level.excellent {{ background: rgba(46,213,115,0.15); color: var(--green); }}
  .risk-card .risk-level.good {{ background: rgba(46,213,115,0.15); color: var(--green); }}
  .risk-card .risk-level.fair {{ background: rgba(255,165,2,0.15); color: var(--orange); }}
  .risk-card .risk-level.poor {{ background: rgba(255,71,87,0.15); color: var(--red); }}
  .risk-card .risk-level.dangerous {{ background: rgba(255,0,0,0.2); color: #ff0000; }}

  /* 风险详情 */
  .risk-detail {{
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 8px; padding: 16px; margin-top: 16px;
  }}
  .risk-detail h3 {{ font-size: 14px; color: #fff; margin-bottom: 12px; }}
  .risk-factor {{
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px 0; border-bottom: 1px solid var(--border);
  }}
  .risk-factor:last-child {{ border-bottom: none; }}
  .risk-factor .factor-name {{ color: var(--text); }}
  .risk-factor .factor-value {{ font-weight: 600; }}
  .risk-factor .factor-value.high {{ color: var(--red); }}
  .risk-factor .factor-value.medium {{ color: var(--orange); }}
  .risk-factor .factor-value.low {{ color: var(--green); }}

  @media print {{
    body {{ background: #fff; color: #333; }}
    .card, section {{ border: 1px solid #ddd; }}
    .card .value {{ color: #333; }}
  }}

  /* 业务报告覆盖样式：低饱和、白底、细线，不使用 AI 仪表盘视觉 */
  :root {{
    --bg: #f4f6f8; --bg2: #ffffff; --bg3: #eef2f6;
    --text: #1f2933; --text2: #4b5563; --text3: #6b7280;
    --accent: #2f4f66; --accent2: #2f4f66;
    --red: #9f3a38; --orange: #9a6a22; --green: #2f6b4f; --blue: #355f7d;
    --border: #d8dee6; --shadow: rgba(31, 41, 51, 0.08);
  }}
  body {{
    background: #f4f6f8; color: #1f2933;
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
  }}
  .container {{ max-width: 1180px; padding: 24px 28px; }}
  .header {{
    background: #fff; border: 1px solid #cfd7df; border-radius: 2px;
    padding: 24px 28px; box-shadow: none;
  }}
  .header::before {{ display: none; }}
  .header h1 {{
    color: #17212b; font-size: 24px; font-weight: 600; letter-spacing: 0.02em;
  }}
  .header h1 span {{ color: #17212b; }}
  .header .subtitle {{ color: #5b6673; font-size: 13px; }}
  .header .meta {{
    border-top: 1px solid #e5e9ef; color: #5b6673; gap: 18px; padding-top: 12px;
  }}
  .cards {{ grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; }}
  .card, section, .chart-box, .scene-card, .responsibility-card,
  .violation-card, .risk-card, .risk-detail, .ai-analysis {{
    background: #fff; border: 1px solid #d8dee6; border-radius: 2px; box-shadow: none;
  }}
  .card {{ padding: 16px; text-align: left; transition: none; }}
  .card:hover {{ transform: none; border-color: #c3ccd6; }}
  .card .value {{ color: #243746; font-size: 30px; font-weight: 600; }}
  .card.red .value, .card.orange .value, .card.green .value {{ color: #243746; }}
  .card .label {{ color: #66717f; font-size: 12px; }}
  section {{ padding: 20px 22px; margin-bottom: 16px; }}
  section h2, .risk-detail h3, .ai-analysis h3, .ai-analysis h4 {{ color: #17212b; }}
  section h2 {{ font-size: 17px; border-bottom: 1px solid #d8dee6; }}
  .section-desc, .footer, .empty, .scene-time, .scene-meta, .vlm-cell {{ color: #697586; }}
  table {{ border: 1px solid #d8dee6; }}
  th {{
    background: #eef2f6; color: #344556; border-bottom: 1px solid #cfd7df;
    font-weight: 600;
  }}
  td {{ color: #1f2933; border-bottom: 1px solid #e5e9ef; }}
  tr:hover td {{ background: #f7f9fb; }}
  .badge, .risk-card .risk-level {{
    border-radius: 2px; border: 1px solid #cfd7df; background: #f5f7f9;
    color: #344556; font-weight: 500;
  }}
  .badge-speeding, .badge-abrupt_stop, .badge-high, .badge-critical,
  .risk-card .risk-level.poor, .risk-card .risk-level.dangerous,
  .factor-value.high, .severity.high {{
    color: #8f3431; background: #fbf1f0; border-color: #e6c2c0;
  }}
  .badge-lane_change, .badge-medium, .risk-card .risk-level.fair,
  .factor-value.medium, .severity.medium {{
    color: #7a571b; background: #faf4e8; border-color: #e5d4ad;
  }}
  .badge-stationary, .badge-congestion, .badge-low,
  .risk-card .risk-level.excellent, .risk-card .risk-level.good,
  .factor-value.low, .severity.low {{
    color: #2f6b4f; background: #edf7f1; border-color: #bfd8c9;
  }}
  .responsibility-title, .responsibility-verdict .verdict-text,
  .violation-title {{ color: #17212b; }}
  .responsibility-verdict {{ background: #f5f7f9; border-radius: 2px; }}
  .violation-icon, .risk-card .risk-icon {{ display: none; }}
  svg text {{ fill: #4b5563; }}
  .footer {{ border-top: 1px solid #d8dee6; margin-top: 8px; }}
</style>
</head>
<body>
<div class="container">

  <div class="header">
    <h1>高速公路车辆追踪<span>分析报告</span></h1>
    <div class="subtitle">高速公路车辆追踪与交通事件分析</div>
    <div class="meta">
      <span>{video.get('video_name', 'N/A')}</span>
      <span>{duration:.1f}s @ {fps:.0f}fps</span>
      <span>{resolution[0]}×{resolution[1]}</span>
      <span>{now}</span>
    </div>
  </div>

  <div class="cards">
    <div class="card"><div class="value">{vehicle_count}</div><div class="label">检测车辆总数</div></div>
    <div class="card red"><div class="value">{event_count}</div><div class="label">异常事件总数</div></div>
    <div class="card orange"><div class="value">{avg_speed:.0f}</div><div class="label">平均速度 (km/h)</div></div>
    <div class="card green"><div class="value">{max_speed:.0f}</div><div class="label">最高速度 (km/h)</div></div>
    <div class="card"><div class="value">{ppm_median:.1f}</div><div class="label">像素/米 比例</div></div>
    <div class="card"><div class="value">{len(events)}</div><div class="label">记录事件数</div></div>
  </div>

  <section>
    <h2>数据统计</h2>
    <p class="section-desc">车辆检测与速度统计的多维分析</p>
    <div class="chart-row">
      <div class="chart-box">
        <h3>事件类型分布</h3>
        {_svg_bar_chart(breakdown)}
      </div>
      <div class="chart-box">
        <h3>速度分布直方图</h3>
        {_svg_speed_histogram(speeds)}
      </div>
    </div>
    <div class="chart-box" style="margin-bottom: 0;">
      <h3>平均速度变化趋势</h3>
      {_svg_speed_curve(data.get('audit_samples', []), fps)}
    </div>
  </section>

  <section>
    <h2>事件时间轴</h2>
    <p class="section-desc">异常事件在时间维度上的分布</p>
    {_svg_event_timeline(events, duration)}
  </section>

  <section>
    <h2>异常事件详情</h2>
    <p class="section-desc">共检测到 {event_count} 个异常事件</p>
    <div style="overflow-x: auto;">
    <table>
      <thead>
        <tr>
          <th>类型</th><th>车辆</th><th>时间</th><th>持续</th>
          <th>详情</th><th>置信度</th><th>VLM复核</th>
        </tr>
      </thead>
      <tbody>{event_rows if event_rows else '<tr><td colspan="7" class="empty">暂无异常事件</td></tr>'}</tbody>
    </table>
    </div>
  </section>

  <section>
    <h2>车辆速度排行 TOP 10</h2>
    <p class="section-desc">按最高速度排序的车辆列表</p>
    <table>
      <thead>
        <tr><th>车辆ID</th><th>平均速度</th><th>最高速度</th><th>首次出现</th><th>最后出现</th><th>跟踪时长</th></tr>
      </thead>
      <tbody>{top_rows if top_rows else '<tr><td colspan="6" class="empty">暂无数据</td></tr>'}</tbody>
    </table>
  </section>

  {scene_html}

  <!-- 事故责任判定模块 -->
  <section>
    <h2>事故责任判定</h2>
    <p class="section-desc">基于事件分析的责任判定与因果关系</p>
    <div class="responsibility-grid">
      {responsibility_html}
    </div>
  </section>

  <!-- 违法行为识别模块 -->
  <section>
    <h2>违法行为识别</h2>
    <p class="section-desc">基于交通法规的违法行为检测</p>
    <div class="violation-grid">
      {violation_html}
    </div>
  </section>

  <!-- 安全风险评估模块 -->
  <section>
    <h2>安全风险评估</h2>
    <p class="section-desc">多维度交通安全风险量化评估</p>
    <div class="risk-assessment">
      {risk_html}
    </div>
  </section>

  {ai_html}

  <section>
    <h2>系统校准信息</h2>
    <p class="section-desc">基于 Sochor 2017 + Kocur 2020 方法的自动标定结果</p>
    <table>
      <thead><tr><th>参数</th><th>值</th><th>说明</th></tr></thead>
      <tbody>
        <tr><td>像素密度 (PPM)</td><td>{ppm_median:.2f}</td><td>每米对应的像素数</td></tr>
        <tr><td>消失点数量</td><td>{vp_count}</td><td>检测到的消失点数</td></tr>
        <tr><td>检测车辆</td><td>{vehicle_count}</td><td>视频中检测到的车辆总数</td></tr>
        <tr><td>分析帧数</td><td>{video.get('frame_count', 0)}</td><td>处理的总帧数</td></tr>
        <tr><td>算法</td><td colspan="2">Kocur 2020/2025 + Sochor 2017 (免标定)</td></tr>
      </tbody>
    </table>
  </section>

  <div class="footer">
    高速公路车辆追踪分析报告 · 生成时间: {now}
  </div>

</div>
</body>
</html>'''


class TrafficReportGenerator:
    def __init__(self, provider: str = "aistudio"):
        self.llm = None
        if LLMClient is None:
            print(f"[LLM] SDK 不可用，跳过文字分析，仅生成 HTML 可视化报告: {LLM_IMPORT_ERROR}")
            return
        try:
            self.llm = LLMClient(provider=provider)
        except Exception as exc:
            print(f"[LLM] 初始化失败，跳过文字分析，仅生成 HTML 可视化报告: {exc}")

    def build_prompt(self, event_data: dict) -> str:
        video = event_data.get("video_info", {})
        events = event_data.get("events", [])
        tracks = event_data.get("tracks", [])

        speeds = [t.get("avg_speed_kmh", 0) for t in tracks if t.get("avg_speed_kmh", 0) > 0]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0

        event_types = {}
        for ev in events:
            etype = ev.get("type", "unknown")
            event_types[etype] = event_types.get(etype, 0) + 1

        event_types_str = ", ".join(f"{k}:{v}" for k, v in event_types.items()) or "none"
        event_lines = [
            f"- {ev.get('type', 'unknown')} @ {ev.get('start_time', ev.get('time_s', 0))}s track={ev.get('track_id', '-')}"
            for ev in events[:8]
        ]

        return f"""你是交通分析报告生成器。根据以下摘要写一份简洁、专业的中文分析，重点给出结论、风险和可执行建议。

视频: {video.get('duration_sec', 0):.1f}s, {video.get('resolution', [0, 0])[0]}x{video.get('resolution', [0, 0])[1]}, fps={video.get('fps', 30)}
车辆数: {len(tracks)}
平均速度: {avg_speed:.1f} km/h
最高速度: {max_speed:.1f} km/h
事件统计: {event_types_str}

事件样本:
{chr(10).join(event_lines) if event_lines else '- none'}

请输出 Markdown，结构固定为:
## 结论
## 关键风险
## 责任与行为判断
## 建议
"""
    def generate(self, event_json_path: str, output_path: str) -> str:
        with open(event_json_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)

        # 如果输出格式是 HTML，生成专业报告
        if output_path.endswith(".html"):
            return self._generate_html_report(event_data, output_path)

        # 默认 Markdown 格式
        prompt = self.build_prompt(event_data)
        if self.llm is None:
            report = "## 结论\n当前环境未配置 LLM SDK，已跳过大模型文字分析。\n"
        else:
            report = self.llm.chat(prompt)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(report)

        return report

    def _generate_html_report(self, event_data: dict, output_path: str) -> str:
        """生成带 AI 分析的专业 HTML 报告。"""
        print("[LLM] 正在生成 AI 智能分析...")
        prompt = self.build_prompt(event_data)
        try:
            ai_analysis = self.llm.chat(prompt) if self.llm is not None else ""
        except Exception as e:
            print(f"[LLM] AI 分析失败: {e}")
            ai_analysis = ""

        print("[HTML] 正在构建可视化报告...")
        events = event_data.get("events", [])
        tracks = event_data.get("tracks", [])
        speeds = [t.get("avg_speed_kmh", 0) for t in tracks if t.get("avg_speed_kmh", 0) > 0]
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        responsibility_html = self._generate_responsibility_html(events)
        violation_html = self._generate_violation_html(events, avg_speed)
        risk_html = self._generate_risk_assessment_html(events, tracks, speeds)
        html = _build_html(event_data, ai_analysis, responsibility_html, violation_html, risk_html)

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        return html
    def generate_html_from_json(self, event_json_path: str, output_path: str) -> str:
        """直接从 JSON 文件生成 HTML 报告。"""
        with open(event_json_path, "r", encoding="utf-8") as f:
            event_data = json.load(f)
        return self._generate_html_report(event_data, output_path)

    def _generate_responsibility_html(self, events: list) -> str:
        """生成事故责任判定HTML。"""
        if not events:
            return '<p class="empty">暂无事件数据</p>'

        html = ""
        # 选择关键事件进行分析
        key_events = [e for e in events if e.get("type") in ["speeding", "abrupt_stop", "lane_change"]][:5]
        
        for ev in key_events:
            etype = ev.get("type", "unknown")
            tid = ev.get("track_id", "?")
            t_start = ev.get("start_time", 0)
            
            # 根据事件类型生成责任判定
            if etype == "speeding":
                speed = ev.get("speed_kmh", 0)
                limit = ev.get("limit_kmh", 60)
                title = f"车辆 #{tid} 超速行驶"
                desc = f"检测到车辆 #{tid} 以 {speed:.0f}km/h 的速度行驶，超过限速 {limit}km/h"
                verdict = "驾驶员负主要责任。超速行驶违反《道路交通安全法》第四十二条，应承担全部责任。"
                severity = "high" if speed > limit * 1.3 else "medium"
            elif etype == "abrupt_stop":
                decel = ev.get("decel_mps2", 0)
                title = f"车辆 #{tid} 紧急制动"
                desc = f"检测到车辆 #{tid} 发生紧急制动，减速度达到 {decel:.1f}m/s²"
                verdict = "需要分析前车状态。如果前车正常行驶，后车因未保持安全距离导致紧急制动，后车负主要责任。"
                severity = "medium"
            elif etype == "lane_change":
                title = f"车辆 #{tid} 频繁变道"
                desc = f"检测到车辆 #{tid} 在短时间内多次变道"
                verdict = "驾驶员负主要责任。频繁变道违反《道路交通安全法实施条例》第四十四条，属于危险驾驶行为。"
                severity = "medium"
            else:
                continue

            html += f'''
            <div class="responsibility-card {severity}">
              <div class="responsibility-header">
                <span class="responsibility-title">{title}</span>
                <span class="responsibility-time">{t_start:.1f}s</span>
              </div>
              <div class="responsibility-body">
                <div class="label">事件描述</div>
                <div class="content">{desc}</div>
                <div class="responsibility-verdict">
                  <div class="verdict-label">责任判定</div>
                  <div class="verdict-text">{verdict}</div>
                </div>
              </div>
            </div>'''

        return html if html else '<p class="empty">暂无关键事件</p>'

    def _generate_violation_html(self, events: list, avg_speed: float) -> str:
        """生成违法行为识别HTML。"""
        if not events:
            return '<p class="empty">暂无事件数据</p>'

        violations = []
        
        # 统计各类事件
        speeding_count = sum(1 for e in events if e.get("type") == "speeding")
        braking_count = sum(1 for e in events if e.get("type") == "abrupt_stop")
        lane_count = sum(1 for e in events if e.get("type") == "lane_change")
        stationary_count = sum(1 for e in events if e.get("type") == "stationary")

        # 超速行驶
        if speeding_count > 0:
            violations.append({
                "type": "speeding",
                "icon": "⚡",
                "title": "超速行驶",
                "desc": f"检测到 {speeding_count} 次超速行为，平均速度 {avg_speed:.0f}km/h",
                "severity": "high" if speeding_count > 3 else "medium",
                "law": "违反《道路交通安全法》第四十二条"
            })

        # 紧急制动
        if braking_count > 0:
            violations.append({
                "type": "braking",
                "icon": "🛑",
                "title": "紧急制动",
                "desc": f"检测到 {braking_count} 次紧急制动，可能存在跟车过近或注意力不集中",
                "severity": "medium",
                "law": "违反《道路交通安全法》第四十三条"
            })

        # 频繁变道
        if lane_count > 0:
            violations.append({
                "type": "lane",
                "icon": "🔄",
                "title": "频繁变道",
                "desc": f"检测到 {lane_count} 次变道行为，可能存在危险驾驶",
                "severity": "medium",
                "law": "违反《道路交通安全法实施条例》第四十四条"
            })

        # 违规停车/低速行驶
        if stationary_count > 0:
            violations.append({
                "type": "stopped",
                "icon": "🚫",
                "title": "违规停车/低速行驶",
                "desc": f"检测到 {stationary_count} 次车辆静止或低速行驶",
                "severity": "low",
                "law": "违反《道路交通安全法实施条例》第六十三条"
            })

        html = ""
        for v in violations:
            html += f'''
            <div class="violation-card">
              <div class="violation-icon {v["type"]}">
                {v["icon"]}
              </div>
              <div class="violation-content">
                <div class="violation-title">{v["title"]}</div>
                <div class="violation-desc">{v["desc"]}</div>
                <div class="violation-meta">
                  <span>危害程度: <span class="severity {v["severity"]}">{v["severity"].upper()}</span></span>
                  <span> · {v["law"]}</span>
                </div>
              </div>
            </div>'''

        return html if html else '<p class="empty">未检测到违法行为</p>'

    def _generate_risk_assessment_html(self, events: list, tracks: list, speeds: list) -> str:
        """生成安全风险评估HTML。"""
        if not speeds:
            return '<p class="empty">暂无数据</p>'

        # 计算风险指标
        avg_speed = sum(speeds) / len(speeds) if speeds else 0
        max_speed = max(speeds) if speeds else 0
        speeding_ratio = sum(1 for s in speeds if s > 60) / len(speeds) if speeds else 0
        
        # 事件统计
        event_count = len(events)
        high_risk_events = sum(1 for e in events if e.get("type") in ["speeding", "abrupt_stop"])
        
        # 速度离散程度
        speed_std = (sum((s - avg_speed) ** 2 for s in speeds) / len(speeds)) ** 0.5 if speeds else 0
        
        # 综合风险评分 (0-100)
        risk_score = min(100, int(
            speeding_ratio * 30 + 
            (high_risk_events / max(len(tracks), 1)) * 25 + 
            speed_std / 10 * 20 +
            (1 if max_speed > 80 else 0) * 25
        ))
        
        # 风险等级
        if risk_score < 20:
            risk_level = "excellent"
            risk_text = "优秀"
        elif risk_score < 40:
            risk_level = "good"
            risk_text = "良好"
        elif risk_score < 60:
            risk_level = "fair"
            risk_text = "一般"
        elif risk_score < 80:
            risk_level = "poor"
            risk_text = "较差"
        else:
            risk_level = "dangerous"
            risk_text = "危险"

        html = f'''
        <div class="risk-card">
          <div class="risk-icon">📊</div>
          <div class="risk-title">综合风险评分</div>
          <div class="risk-value">{risk_score}</div>
          <div class="risk-level {risk_level}">{risk_text}</div>
        </div>
        <div class="risk-card">
          <div class="risk-icon">⚡</div>
          <div class="risk-title">超速风险</div>
          <div class="risk-value">{speeding_ratio*100:.0f}%</div>
          <div class="risk-level {"high" if speeding_ratio > 0.3 else "medium" if speeding_ratio > 0.1 else "low"}">
            {"高" if speeding_ratio > 0.3 else "中" if speeding_ratio > 0.1 else "低"}
          </div>
        </div>
        <div class="risk-card">
          <div class="risk-icon">🛑</div>
          <div class="risk-title">行为风险</div>
          <div class="risk-value">{high_risk_events}</div>
          <div class="risk-level {"high" if high_risk_events > 5 else "medium" if high_risk_events > 2 else "low"}">
            {"高" if high_risk_events > 5 else "中" if high_risk_events > 2 else "低"}
          </div>
        </div>
        <div class="risk-card">
          <div class="risk-icon">📈</div>
          <div class="risk-title">速度离散度</div>
          <div class="risk-value">{speed_std:.1f}</div>
          <div class="risk-level {"high" if speed_std > 20 else "medium" if speed_std > 10 else "low"}">
            {"高" if speed_std > 20 else "中" if speed_std > 10 else "低"}
          </div>
        </div>
        </div>
        <div class="risk-detail">
          <h3>风险因素详情</h3>
          <div class="risk-factor">
            <span class="factor-name">平均速度</span>
            <span class="factor-value">{avg_speed:.1f} km/h</span>
          </div>
          <div class="risk-factor">
            <span class="factor-name">最高速度</span>
            <span class="factor-value {"high" if max_speed > 80 else "medium" if max_speed > 60 else "low"}">{max_speed:.1f} km/h</span>
          </div>
          <div class="risk-factor">
            <span class="factor-name">超速车辆比例</span>
            <span class="factor-value {"high" if speeding_ratio > 0.3 else "medium" if speeding_ratio > 0.1 else "low"}">{speeding_ratio*100:.1f}%</span>
          </div>
          <div class="risk-factor">
            <span class="factor-name">高风险事件数</span>
            <span class="factor-value {"high" if high_risk_events > 5 else "medium" if high_risk_events > 2 else "low"}">{high_risk_events}</span>
          </div>
          <div class="risk-factor">
            <span class="factor-name">速度标准差</span>
            <span class="factor-value {"high" if speed_std > 20 else "medium" if speed_std > 10 else "low"}">{speed_std:.2f} km/h</span>
          </div>
        </div>'''

        return html

