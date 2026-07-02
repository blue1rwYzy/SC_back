"""
访客记录服务
负责记录访问IP、地理位置等信息
"""
import sqlite3
import os
from datetime import datetime
from typing import Optional, Dict, List
import requests
from contextlib import contextmanager

# SQLite数据库路径
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "visitor_records.db")

class VisitorService:
    """访客记录服务"""

    def __init__(self):
        """初始化数据库"""
        self.init_database()

    @contextmanager
    def get_connection(self):
        """获取数据库连接的上下文管理器"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # 使结果可以通过列名访问
        try:
            yield conn
        finally:
            conn.close()

    def init_database(self):
        """初始化数据库表"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 创建访客记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS visitor_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    country TEXT,
                    province TEXT,
                    city TEXT,
                    isp TEXT,
                    latitude REAL,
                    longitude REAL,
                    user_agent TEXT,
                    endpoint TEXT,
                    visit_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ip_address
                ON visitor_records(ip_address)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_visit_time
                ON visitor_records(visit_time)
            """)

            conn.commit()
            print(f"✅ 访客记录数据库初始化完成: {DB_PATH}")

    def get_ip_location(self, ip: str) -> Dict:
        """
        获取IP地理位置信息
        使用高德地图IP定位API
        """
        # 本地IP直接返回
        if ip in ['127.0.0.1', 'localhost', '::1']:
            return {
                'country': '中国',
                'province': '本地',
                'city': '本地',
                'isp': '本地网络',
                'latitude': 39.9042,
                'longitude': 116.4074
            }

        try:
            # 使用高德地图IP定位API
            # API文档: https://lbs.amap.com/api/webservice/guide/api/ipconfig
            amap_key = 'be8291ff689aa062931f30bb99aad37a'
            response = requests.get(
                f'https://restapi.amap.com/v3/ip?ip={ip}&key={amap_key}',
                timeout=5
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('status') == '1' and data.get('province'):
                    # 解析位置信息
                    province = data.get('province', '未知')
                    city = data.get('city', '未知')

                    # 如果province和city相同(直辖市),只保留省份
                    if province == city:
                        city = province

                    # 解析经纬度 (高德返回的是"经度,纬度"格式的字符串)
                    location_str = data.get('rectangle', '')
                    latitude = None
                    longitude = None
                    if location_str:
                        try:
                            # rectangle格式: "116.0119343,39.66127144;116.7829835,40.2164962"
                            # 取中心点
                            coords = location_str.split(';')
                            if len(coords) == 2:
                                left_bottom = coords[0].split(',')
                                right_top = coords[1].split(',')
                                longitude = (float(left_bottom[0]) + float(right_top[0])) / 2
                                latitude = (float(left_bottom[1]) + float(right_top[1])) / 2
                        except Exception as e:
                            print(f"⚠️ 解析经纬度失败: {e}")

                    return {
                        'country': '中国',  # 高德主要服务中国区域
                        'province': province,
                        'city': city,
                        'isp': data.get('adcode', '未知'),  # 高德返回区域编码
                        'latitude': latitude,
                        'longitude': longitude
                    }
        except Exception as e:
            print(f"⚠️ 高德地图API调用失败: {e}")

        # 如果高德API失败,尝试备用API
        try:
            response = requests.get(
                f'http://ip-api.com/json/{ip}?lang=zh-CN',
                timeout=3
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'success':
                    return {
                        'country': data.get('country', '未知'),
                        'province': data.get('regionName', '未知'),
                        'city': data.get('city', '未知'),
                        'isp': data.get('isp', '未知'),
                        'latitude': data.get('lat'),
                        'longitude': data.get('lon')
                    }
        except Exception as e:
            print(f"⚠️ 备用API也失败: {e}")

        # 如果所有API都失败,返回默认值
        return {
            'country': '未知',
            'province': '未知',
            'city': '未知',
            'isp': '未知',
            'latitude': None,
            'longitude': None
        }

    def record_visit(self, ip: str, user_agent: Optional[str] = None, endpoint: Optional[str] = None):
        """
        记录访问

        Args:
            ip: 访问者IP地址
            user_agent: 用户代理信息
            endpoint: 访问的端点
        """
        try:
            # 获取地理位置信息
            location = self.get_ip_location(ip)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO visitor_records
                    (ip_address, country, province, city, isp, latitude, longitude, user_agent, endpoint, visit_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ip,
                    location['country'],
                    location['province'],
                    location['city'],
                    location['isp'],
                    location['latitude'],
                    location['longitude'],
                    user_agent,
                    endpoint,
                    datetime.now()
                ))
                conn.commit()
                print(f"📍 记录访问: {ip} ({location['province']}-{location['city']})")
        except Exception as e:
            print(f"❌ 记录访问失败: {e}")

    def get_visit_statistics(self) -> Dict:
        """
        获取访问统计数据
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # 1. 总访问次数
            cursor.execute("SELECT COUNT(*) as total FROM visitor_records")
            total_visits = cursor.fetchone()['total']

            # 2. 独立访客数(不同IP)
            cursor.execute("SELECT COUNT(DISTINCT ip_address) as unique_ips FROM visitor_records")
            unique_visitors = cursor.fetchone()['unique_ips']

            # 3. 今日访问
            cursor.execute("""
                SELECT COUNT(*) as today_visits
                FROM visitor_records
                WHERE DATE(visit_time) = DATE('now', 'localtime')
            """)
            today_visits = cursor.fetchone()['today_visits']

            # 4. 本周访问
            cursor.execute("""
                SELECT COUNT(*) as week_visits
                FROM visitor_records
                WHERE visit_time >= DATE('now', 'localtime', '-7 days')
            """)
            week_visits = cursor.fetchone()['week_visits']

            # 5. 按省份统计
            cursor.execute("""
                SELECT province, COUNT(*) as count
                FROM visitor_records
                WHERE province IS NOT NULL AND province != '未知'
                GROUP BY province
                ORDER BY count DESC
                LIMIT 20
            """)
            province_stats = [dict(row) for row in cursor.fetchall()]

            # 6. 按城市统计
            cursor.execute("""
                SELECT city, province, COUNT(*) as count
                FROM visitor_records
                WHERE city IS NOT NULL AND city != '未知'
                GROUP BY city, province
                ORDER BY count DESC
                LIMIT 20
            """)
            city_stats = [dict(row) for row in cursor.fetchall()]

            # 7. 最近7天每日访问趋势
            cursor.execute("""
                SELECT DATE(visit_time) as date, COUNT(*) as count
                FROM visitor_records
                WHERE visit_time >= DATE('now', 'localtime', '-7 days')
                GROUP BY DATE(visit_time)
                ORDER BY date
            """)
            daily_trends = [dict(row) for row in cursor.fetchall()]

            # 8. 地图数据 - 获取所有有坐标的访问记录(按城市聚合)
            cursor.execute("""
                SELECT
                    city,
                    province,
                    country,
                    latitude,
                    longitude,
                    COUNT(*) as visit_count
                FROM visitor_records
                WHERE latitude IS NOT NULL
                    AND longitude IS NOT NULL
                GROUP BY city, province, country, latitude, longitude
                ORDER BY visit_count DESC
            """)
            map_data = [dict(row) for row in cursor.fetchall()]

            return {
                'total_visits': total_visits,
                'unique_visitors': unique_visitors,
                'today_visits': today_visits,
                'week_visits': week_visits,
                'province_stats': province_stats,
                'city_stats': city_stats,
                'daily_trends': daily_trends,
                'map_data': map_data
            }

    def get_recent_visitors(self, limit: int = 50) -> List[Dict]:
        """
        获取最近访客记录

        Args:
            limit: 返回数量限制
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    id, ip_address, country, province, city, isp,
                    latitude, longitude, user_agent, endpoint, visit_time
                FROM visitor_records
                ORDER BY visit_time DESC
                LIMIT ?
            """, (limit,))

            return [dict(row) for row in cursor.fetchall()]


# 创建全局实例
visitor_service = VisitorService()
