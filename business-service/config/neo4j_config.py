"""
Neo4j 配置
知识图谱模块通过业务服务内部调用 Neo4j HTTP API，
不新增独立后端服务端口。
"""
import os


NEO4J_HTTP_URL = os.getenv("NEO4J_HTTP_URL", "http://127.0.0.1:7474").rstrip("/")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "12345678")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")
NEO4J_TIMEOUT = int(os.getenv("NEO4J_TIMEOUT", "30"))


def get_neo4j_tx_commit_url() -> str:
    """获取 Neo4j 事务提交接口 URL"""
    return f"{NEO4J_HTTP_URL}/db/{NEO4J_DATABASE}/tx/commit"

