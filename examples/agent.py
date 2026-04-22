#!/usr/bin/env python3
"""
Agent — interactive agent loop built on codex_backend_sdk.

Features
--------
- @agent.tool      : register a function as a tool; spec lives in its YAML docstring
- Agent.interact   : multi-turn REPL with automatic tool dispatch and re-prompting
- Reasoning        : pass reasoning= / reasoning_summary= to the constructor
- Parallel tools   : the model may call several tools in one pass

Docstring format (YAML)
-----------------------
    description: One-line description shown to the model.
    parameters:
      param_name:
        type: string | integer | number | boolean | array | object
        description: What this param is.
        enum: [opt1, opt2]      # optional
    required: [param_name]      # optional, defaults to []

Quick start
-----------
    from codex_backend_sdk import CodexClient
    from examples.agent import Agent

    client = CodexClient().authenticate()
    agent  = Agent(client, reasoning="low")

    @agent.tool
    def calculator(expression: str) -> dict:
        \"\"\"
        description: Evaluate a Python arithmetic expression.
        parameters:
          expression:
            type: string
            description: A safe arithmetic expression, e.g. "2 ** 10 + 3"
        required: [expression]
        \"\"\"
        return {"result": eval(expression, {"__builtins__": {}})}

    agent.interact()
"""

from __future__ import annotations

import inspect
import json
import sys
from typing import Any, Callable

import yaml

from codex_backend_sdk import (
    CodexClient,
    ReasoningDelta,
    ResponseCompleted,
    ResponseFailed,
    TextDelta,
    ToolCall,
)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_DIM   = "\033[2m"
_AMBER = "\033[33m"
_RED   = "\033[31m"


class Agent:
    """
    Interactive agent loop with automatic tool dispatch.

    Parameters
    ----------
    client : CodexClient
        Authenticated Codex client.
    instructions : str
        System prompt prepended to every request.
    reasoning : str | None
        Reasoning effort passed to the model: "minimal" | "low" | "medium" |
        "high" | "xhigh".
    reasoning_summary : str | None
        "concise" | "detailed" | "auto" — streams reasoning summaries when set.
    model : str | None
        Override the client's default model for this agent.
    parallel_tool_calls : bool
        Allow the model to call multiple tools per turn (default True).
    """

    def __init__(
        self,
        client: CodexClient,
        *,
        instructions: str = "",
        reasoning: str | None = None,
        reasoning_summary: str | None = None,
        model: str | None = None,
        parallel_tool_calls: bool = True,
    ) -> None:
        self._client = client
        self._instructions = instructions
        self._reasoning = reasoning
        self._reasoning_summary = reasoning_summary
        self._model = model
        self._parallel = parallel_tool_calls
        self._tools: dict[str, Callable] = {}
        self._tool_defs: list[dict] = []

    # ------------------------------------------------------------------
    # Tool registration
    # ------------------------------------------------------------------

    def tool(self, func: Callable) -> Callable:
        """
        Register a function as a tool for this agent.  Use as a decorator:

            @agent.tool
            def my_tool(...): ...

        The function's docstring must be a YAML mapping with keys:
        description, parameters, required.
        """
        doc = inspect.getdoc(func)
        if not doc:
            raise ValueError(f"@agent.tool: {func.__name__} must have a docstring")
        try:
            spec = yaml.safe_load(doc)
        except yaml.YAMLError as exc:
            raise ValueError(f"@agent.tool: {func.__name__} docstring is not valid YAML") from exc
        if not isinstance(spec, dict):
            raise ValueError(f"@agent.tool: {func.__name__} docstring must be a YAML mapping")

        name = str(spec.get("name", func.__name__))
        description = str(spec.get("description", ""))
        required = list(spec.get("required", []))

        properties: dict[str, dict] = {}
        for param_name, meta in (spec.get("parameters") or {}).items():
            prop: dict[str, Any] = {}
            for key in ("type", "description", "enum", "items", "default"):
                if key in meta:
                    prop[key] = meta[key]
            properties[param_name] = prop

        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = func
        self._tool_defs.append({
            "type": "function",
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        })
        return func

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dispatch(self, call: ToolCall) -> str:
        """Call the registered function and return a JSON string result."""
        func = self._tools.get(call.name)
        if func is None:
            return json.dumps({"error": f"unknown tool: {call.name}"})
        try:
            result = func(**call.parsed_arguments())
            return result if isinstance(result, str) else json.dumps(result)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": type(exc).__name__, "detail": str(exc)})

    def _stream_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "parallel_tool_calls": self._parallel,
            "include_reasoning": bool(self._reasoning_summary),
        }
        if self._tool_defs:
            kwargs["tools"] = self._tool_defs
        if self._instructions:
            kwargs["instructions"] = self._instructions
        if self._reasoning:
            kwargs["reasoning"] = self._reasoning
        if self._reasoning_summary:
            kwargs["reasoning_summary"] = self._reasoning_summary
        if self._model:
            kwargs["model"] = self._model
        return kwargs

    def _tool_round(self, context: list[dict]) -> tuple[str, bool]:
        """
        Run one stream call against the current context.
        Returns (assistant_text, had_tool_calls).
        Tool items are appended to *context* in-place.
        """
        text = ""
        had_tools = False

        print("\nassistant> ", end="", flush=True)

        for event in self._client.stream(None, conversation_history=context, **self._stream_kwargs()):
            if isinstance(event, TextDelta):
                print(event.text, end="", flush=True)
                text += event.text

            elif isinstance(event, ReasoningDelta):
                print(f"{_DIM}[thinking] {event.text}{_RESET}", end="", flush=True)

            elif isinstance(event, ToolCall):
                had_tools = True
                print(f"\n{_AMBER}[tool] {event.name}({event.arguments}){_RESET}")
                output = self._dispatch(event)
                print(f"{_AMBER}[result] {output}{_RESET}")
                context.append(event.as_history_item())
                context.append(event.to_tool_result(output))

            elif isinstance(event, ResponseCompleted):
                parts = [f"in={event.input_tokens}", f"out={event.output_tokens}"]
                if event.usage.reasoning_tokens:
                    parts.append(f"reasoning={event.usage.reasoning_tokens}")
                print(f"\n{_DIM}[{' '.join(parts)}]{_RESET}")

            elif isinstance(event, ResponseFailed):
                print(f"\n{_RED}[failed: {event.code}] {event.message}{_RESET}")
                return text, False

        return text, had_tools

    # ------------------------------------------------------------------
    # Public: interactive REPL
    # ------------------------------------------------------------------

    def interact(self, *, welcome: str = "Agent ready — type 'quit' to exit.") -> None:
        """Launch the interactive chat loop."""
        print(welcome)
        context: list[dict] = []

        while True:
            try:
                user_input = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nBye.")
                break

            if user_input.lower() in ("quit", "exit", "q"):
                break
            if not user_input:
                continue

            # Append user turn before streaming so subsequent tool rounds see it
            context.append({
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": user_input}],
            })

            # Tool loop: keep streaming until the model stops calling tools
            final_text = ""
            while True:
                turn_text, had_tools = self._tool_round(context)
                if turn_text:
                    final_text = turn_text
                if not had_tools:
                    break

            if final_text:
                context.append({
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": final_text}],
                })


# ---------------------------------------------------------------------------
# Demo — run directly: python -m examples.agent  (or python examples/agent.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import math

    client = CodexClient().authenticate()
    print(f"Authenticated as: {client._store.email}\n")

    agent = Agent(
        client,
        instructions=(
            "You are a helpful assistant with access to a calculator and a weather tool. "
            "Always use a tool when a user asks for a calculation or weather information."
        ),
        reasoning="low",
        parallel_tool_calls=True,
    )

    # ------------------------------------------------------------------ tools

    @agent.tool
    def calculator(expression: str) -> dict:
        """
        description: Evaluate a safe Python arithmetic expression and return the result.
        parameters:
          expression:
            type: string
            description: >
              A Python arithmetic expression using numbers and operators
              (+, -, *, /, **, %, sqrt via math). E.g. "2 ** 10 + math.sqrt(16)".
        required: [expression]
        """
        try:
            result = eval(expression, {"__builtins__": {}, "math": math})  # noqa: S307
            return {"result": result}
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}

    @agent.tool
    def get_weather(city: str, unit: str = "celsius") -> dict:
        """
        description: Get the current weather for a given city (fake data for demo).
        parameters:
          city:
            type: string
            description: City name, e.g. Paris, Tokyo, New York.
          unit:
            type: string
            description: Temperature unit.
            enum: [celsius, fahrenheit]
        required: [city]
        """
        data = {
            "paris":    {"temperature": 18, "condition": "cloudy"},
            "tokyo":    {"temperature": 27, "condition": "sunny"},
            "new york": {"temperature": 22, "condition": "partly cloudy"},
            "london":   {"temperature": 14, "condition": "rainy"},
        }
        weather = data.get(city.lower(), {"temperature": 15, "condition": "unknown"})
        temp = weather["temperature"]
        if unit == "fahrenheit":
            temp = round(temp * 9 / 5 + 32, 1)
        return {"city": city, "temperature": temp, "unit": unit, "condition": weather["condition"]}

    # -------------------------------------------------------------- start REPL

    agent.interact(
        welcome=(
            "Demo agent — tools available: calculator, get_weather\n"
            "Try: 'What's the weather in Paris and Tokyo?' or '2^32 + sqrt(144)'\n"
            "Type 'quit' to exit."
        )
    )
