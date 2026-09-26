"""A scripted stand-in for the Ollama client."""

import json
from collections.abc import Callable
from typing import Any

from app.agent.llm import LLMReply, ToolCall

Step = LLMReply | Callable[[list[dict[str, Any]]], LLMReply]


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(name=name, arguments=arguments)


def tools(*calls: ToolCall) -> LLMReply:
    return LLMReply(content="", tool_calls=list(calls))


def say(text: str) -> LLMReply:
    return LLMReply(content=text, tool_calls=[])


def tool_results(messages: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    return [json.loads(m["content"]) for m in messages if m.get("tool_name") == name]


class FakeLLM:
    """Replays ``steps`` in order; a step may be a function of the messages so far."""

    def __init__(self, *steps: Step) -> None:
        self.steps = list(steps)
        self.requests: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        self.requests.append([dict(m) for m in messages])
        if not self.steps:
            raise AssertionError("FakeLLM ran out of scripted steps")
        step = self.steps.pop(0)
        return step(messages) if callable(step) else step


class LoopingLLM:
    """Always asks for another tool call."""

    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        self.calls += 1
        return LLMReply(content="", tool_calls=[call("get_expenses")])
