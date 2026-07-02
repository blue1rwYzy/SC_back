"""VLM（视觉大模型）客户端，用于关键帧复核。支持 AI Studio / Gemini。"""
import os
try:
    from openai import OpenAI
except Exception as exc:
    OpenAI = None
    OPENAI_IMPORT_ERROR = exc
else:
    OPENAI_IMPORT_ERROR = None

from utils.image_encode import image_to_base64


class VLMClient:
    def __init__(self, provider: str = "aistudio"):
        self.provider = provider
        self.client = None
        self.model = ""

        if OpenAI is None:
            self.disabled_reason = f"OpenAI SDK 不可用: {OPENAI_IMPORT_ERROR}"
            print(f"[VLM] {self.disabled_reason}")
            return
        self.disabled_reason = ""
        timeout = float(os.getenv("TRACKING_VLM_TIMEOUT", "8"))

        if provider == "aistudio":
            api_key = os.getenv("AI_STUDIO_API_KEY")
            if not api_key:
                self.disabled_reason = "未配置 AI_STUDIO_API_KEY，跳过 VLM 关键帧复核"
                print(f"[VLM] {self.disabled_reason}")
                return
            self.client = OpenAI(
                api_key=api_key,
                base_url=os.getenv(
                    "AI_STUDIO_BASE_URL",
                    "https://aistudio.baidu.com/llm/lmapi/v3"
                ),
                timeout=timeout,
                max_retries=0,
            )
            self.model = os.getenv("AI_STUDIO_VLM_MODEL", "ernie-4.5-turbo-vl")

        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                self.disabled_reason = "未配置 GEMINI_API_KEY，跳过 VLM 关键帧复核"
                print(f"[VLM] {self.disabled_reason}")
                return
            self.client = OpenAI(
                api_key=api_key,
                base_url=os.getenv(
                    "GEMINI_BASE_URL",
                    "https://generativelanguage.googleapis.com/v1beta/openai/"
                ),
                timeout=timeout,
                max_retries=0,
            )
            self.model = os.getenv("GEMINI_VLM_MODEL", "gemini-2.5-flash")

        else:
            raise ValueError(f"Unsupported VLM provider: {provider}")

    def verify_keyframe(
        self, image_path: str, event_type: str, event_desc: str
    ) -> dict:
        """对关键帧进行视觉复核，返回结构化结果。"""
        if self.client is None:
            return {
                "support": None,
                "explanation": self.disabled_reason or "VLM 未初始化",
                "risk_level": "unknown",
                "confidence": 0.0,
            }

        image_b64 = image_to_base64(image_path)

        prompt = f"""请分析这张交通监控关键帧。

系统初步检测事件：
- 事件类型：{event_type}
- 事件描述：{event_desc}

请回答：
1. 图中是否支持这个事件判断？
2. 是否存在拥堵、违停、事故、占道、异常停车等情况？
3. 如果证据不足，请说明原因。
4. 给出 0 到 1 的复核置信度。
5. 输出 JSON，字段包括 support, explanation, risk_level, confidence。
"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
                temperature=0.2,
            )
            return {"raw_response": response.choices[0].message.content}
        except Exception as e:
            return {"error": str(e)}
