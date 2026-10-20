from langchain_anthropic import ChatAnthropic

from ..config import settings


def make_model(model: str) -> ChatAnthropic:
    # The key comes from settings (.env); pydantic-settings does not export it to os.environ,
    # so ChatAnthropic wouldn't find it on its own.
    return ChatAnthropic(model=model, api_key=settings.anthropic_api_key)
