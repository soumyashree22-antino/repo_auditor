import os

import requests
from dotenv import load_dotenv

load_dotenv()


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
        self.nvidia_model = os.getenv("NVIDIA_MODEL", "qwen2_5-coder-32b-instruct")
        self.timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT", "300"))
        self.num_ctx = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "4096"))

    def call(self, system_prompt: str, user_message: str, max_tokens: int = 4000) -> str:
        if self.provider == "anthropic":
            return self.call_anthropic(system_prompt, user_message, max_tokens)
        elif self.provider == "nvidia":
            result = self.call_nvidia(system_prompt, user_message, max_tokens)
            if result:  # If NVIDIA succeeds, return result
                return result
            # Fallback to Ollama if NVIDIA fails
            return self.call_ollama(system_prompt, user_message, max_tokens)
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

        response = requests.post(f"{self.ollama_url}/api/generate", json=payload, timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("response", "").strip()

    def call_nvidia(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        """Call NVIDIA API with the specified model."""
        if not self.nvidia_api_key:
            raise ValueError("NVIDIA_API_KEY not set in environment variables")

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
            response = requests.post(api_url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"].strip()
            return ""
        except requests.exceptions.HTTPError as error:
            if error.response.status_code == 404:
                print(f"NVIDIA API Error: Model '{self.nvidia_model}' not found or endpoint incorrect")
                print(f"Try using 'meta/llama-2-7b-chat' or check https://docs.api.nvidia.com for available models")
            else:
                print(f"NVIDIA API HTTP Error: {error}")
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
