"""LLM 客户端，支持百度 AI Studio / OpenRouter / Gemini，均通过 OpenAI SDK 兼容调用。"""
import os
try:
    from openai import OpenAI
except Exception as exc:
    OpenAI = None
    OPENAI_IMPORT_ERROR = exc
else:
    OPENAI_IMPORT_ERROR = None


class LLMClient:
    def __init__(self, provider: str = "aistudio"):
        self.provider = provider
        self.client = None
        self.model = ""
        self.disabled_reason = ""

        if OpenAI is None:
            self.disabled_reason = f"OpenAI SDK 不可用: {OPENAI_IMPORT_ERROR}"
            print(f"[LLM] {self.disabled_reason}")
            return

        timeout = float(os.getenv("TRACKING_LLM_TIMEOUT", "8"))

        if provider == "aistudio":
            api_key = os.getenv("AI_STUDIO_API_KEY")
            if not api_key:
                self.disabled_reason = "未配置 AI_STUDIO_API_KEY，跳过 LLM 报告增强"
                print(f"[LLM] {self.disabled_reason}")
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
            self.model = os.getenv("AI_STUDIO_MODEL", "ernie-3.5-8k")

        elif provider == "openrouter":
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                self.disabled_reason = "未配置 OPENROUTER_API_KEY，跳过 LLM 报告增强"
                print(f"[LLM] {self.disabled_reason}")
                return
            self.client = OpenAI(
                api_key=api_key,
                base_url=os.getenv(
                    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
                ),
                timeout=timeout,
                max_retries=0,
            )
            self.model = os.getenv("OPENROUTER_MODEL", "openrouter/free")

        elif provider == "gemini":
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                self.disabled_reason = "未配置 GEMINI_API_KEY，跳过 LLM 报告增强"
                print(f"[LLM] {self.disabled_reason}")
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
            self.model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    def chat(self, prompt: str, system_prompt: str = "你是智能交通分析专家。") -> str:
        if self.client is None:
            raise RuntimeError(self.disabled_reason or "LLM 未初始化")

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content
