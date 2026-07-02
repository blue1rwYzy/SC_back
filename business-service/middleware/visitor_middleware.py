"""
访客记录中间件
自动记录所有API访问
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from services.visitor_service import visitor_service
import asyncio


class VisitorMiddleware(BaseHTTPMiddleware):
    """访客记录中间件"""

    # 排除不需要记录的路径
    EXCLUDED_PATHS = {
        '/docs',
        '/redoc',
        '/openapi.json',
        '/uploads',
        '/favicon.ico',
    }

    async def dispatch(self, request: Request, call_next):
        """处理请求"""
        # 获取客户端IP
        client_ip = self.get_client_ip(request)

        # 获取请求路径
        path = request.url.path

        # 检查是否需要记录
        should_record = not any(path.startswith(excluded) for excluded in self.EXCLUDED_PATHS)

        if should_record and client_ip:
            # 在后台异步记录访问(不阻塞请求)
            user_agent = request.headers.get('user-agent')
            endpoint = f"{request.method} {path}"

            # 使用线程池异步记录,避免阻塞主线程
            asyncio.create_task(
                asyncio.to_thread(
                    visitor_service.record_visit,
                    client_ip,
                    user_agent,
                    endpoint
                )
            )

        # 继续处理请求
        response = await call_next(request)
        return response

    def get_client_ip(self, request: Request) -> str:
        """
        获取客户端真实IP地址
        考虑代理、负载均衡等情况
        """
        # 优先从X-Forwarded-For获取(nginx反向代理)
        forwarded = request.headers.get('X-Forwarded-For')
        if forwarded:
            # X-Forwarded-For可能包含多个IP,取第一个
            return forwarded.split(',')[0].strip()

        # 其他代理头
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip

        # 直接连接的客户端IP
        if request.client:
            return request.client.host

        return 'unknown'
