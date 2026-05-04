import os

import requests
from dotenv import load_dotenv

load_dotenv()

# Separate timeouts: cloud APIs respond fast; Ollama runs locally and may be slower
_NVIDIA_TIMEOUT = int(os.getenv("NVIDIA_TIMEOUT", "60"))
_OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))


class LLMClient:
    """Provider-agnostic client for Ollama, Anthropic, or NVIDIA API calls."""

    def __init__(
        self,
        provider: str | None = None,
        ollama_url: str | None = None,
        ollama_model: str | None = None,
        timeout: int | None = None,
        num_ctx: int | None = None,
    ) -> None:
        self.provider = (provider or os.getenv("LLM_PROVIDER", "nvidia")).lower().strip()
        self.ollama_url = (ollama_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.ollama_model = ollama_model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
        self.nvidia_api_key = os.getenv("NVIDIA_API_KEY")
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
        self.nvidia_timeout = timeout or _NVIDIA_TIMEOUT
        self.ollama_timeout = timeout or _OLLAMA_TIMEOUT
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "4096"))

    def call(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
        if self.provider == "anthropic":
            return self.call_anthropic(system_prompt, user_message, max_tokens)
        elif self.provider == "nvidia":
            # On Streamlit Cloud, Ollama is not available — do NOT fall back to it.
            # If NVIDIA fails, return "" and let the caller use its own fallback.
            if not self.nvidia_api_key:
                print("NVIDIA_API_KEY is not set. Skipping LLM call.")
                return ""
            return self.call_nvidia(system_prompt, user_message, max_tokens)
        # Default: Ollama (local)
        return self.call_ollama(system_prompt, user_message, max_tokens)

    def call_ollama(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        prompt = f"{system_prompt}\n\nUSER INPUT:\n{user_message}"
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx,
            },
        }

        response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=self.ollama_timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def call_nvidia(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        """Call NVIDIA API with the specified model."""
        if not self.nvidia_api_key:
            print("NVIDIA_API_KEY is not set. Skipping NVIDIA call.")
            return ""

        api_url = "https://integrate.api.nvidia.com/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.nvidia_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.nvidia_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
            "top_p": 0.7,
        }

        try:
            response = requests.post(api_url, json=payload, headers=headers, timeout=self.nvidia_timeout)
            response.raise_for_status()
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            return ""
        except requests.exceptions.HTTPError as error:
            status = error.response.status_code if error.response is not None else "unknown"
            if status == 404:
                print(f"NVIDIA API Error: Model '{self.nvidia_model}' not found.")
                print("Check available models at: https://build.nvidia.com/explore/discover")
            elif status == 401:
                print("NVIDIA API Error: Invalid or expired API key (401 Unauthorized).")
            elif status == 402:
                print("NVIDIA API Error: Usage limit reached (402). Check your NVIDIA account.")
            else:
                print(f"NVIDIA API HTTP Error {status}: {error}")
            return ""
        except requests.exceptions.Timeout:
            print(f"NVIDIA API timed out after {self.nvidia_timeout}s.")
            return ""
        except requests.exceptions.RequestException as error:
            print(f"NVIDIA API call failed: {error}")
            return ""

    def call_anthropic(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or api_key.startswith("sk-ant-your"):
            return ""

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text.strip()


def call_llm(system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
    return LLMClient().call(system_prompt, user_message, max_tokens)


def call_ollama(system_prompt: str, user_message: str, max_tokens: int) -> str:
    return LLMClient().call_ollama(system_prompt, user_message, max_tokens)


def call_nvidia(system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
    return LLMClient(provider="nvidia").call_nvidia(system_prompt, user_message, max_tokens)


def call_anthropic(system_prompt: str, user_message: str, max_tokens: int) -> str:
    return LLMClient(provider="anthropic").call_anthropic(system_prompt, user_message, max_tokens)
