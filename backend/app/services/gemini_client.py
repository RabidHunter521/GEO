import google.generativeai as genai
import structlog

logger = structlog.get_logger()

MODEL_NAME = "gemini-2.0-flash"


class GeminiClient:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(MODEL_NAME)

    def query(self, prompt: str) -> str:
        last_exc = None
        for attempt in range(2):
            try:
                response = self._model.generate_content(prompt)
                return response.text
            except Exception as exc:
                last_exc = exc
                logger.warning("gemini_query_failed", attempt=attempt + 1, error=str(exc))
        raise last_exc
