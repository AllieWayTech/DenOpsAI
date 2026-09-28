from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol


class PlanningProvider(Protocol):
    def create_plan(self, task: str, policy: str) -> str: ...


@dataclass(frozen=True)
class OpenAIPlanningProvider:
    api_key: str
    model: str = "gpt-6-sol"
    max_output_tokens: int = 800

    def create_plan(self, task: str, policy: str) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key, timeout=120.0, max_retries=2)
        response = client.responses.create(
            model=self.model,
            reasoning={"effort": "low"},
            text={"verbosity": "low"},
            store=False,
            max_output_tokens=self.max_output_tokens,
            input=[
                {
                    "role": "developer",
                    "content": (
                        "You are the planning stage of the DenOps AI builder. "
                        "Follow the supplied policy. Produce a concise implementation plan "
                        "for human review. Do not claim to have edited files, run commands, "
                        "or completed the task. Include scope, files likely affected, tests, "
                        "risks, and explicit reasons to block if the task violates policy."
                    ),
                },
                {
                    "role": "user",
                    "content": f"BUILDER POLICY:\n{policy}\n\nOWNER TASK:\n{task}",
                },
            ],
        )
        plan = response.output_text.strip()
        if not plan:
            raise RuntimeError("OpenAI returned an empty plan")
        return plan


def provider_from_environment(
    environment: dict[str, str] | None = None,
) -> PlanningProvider:
    values = os.environ if environment is None else environment
    provider = values.get("DENOPS_AI_PROVIDER", "openai")
    if provider != "openai":
        raise RuntimeError(f"planning provider is not implemented: {provider}")
    api_key = values.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    if values.get("DENOPS_AI_OPENAI_ENABLED") != "1":
        raise RuntimeError("OpenAI test calls are disabled")
    try:
        requested_output = int(values.get("DENOPS_AI_MAX_OUTPUT_TOKENS", "800"))
    except ValueError as error:
        raise RuntimeError("DENOPS_AI_MAX_OUTPUT_TOKENS must be an integer") from error
    max_output_tokens = min(max(requested_output, 1), 1000)
    return OpenAIPlanningProvider(
        api_key=api_key,
        model=values.get("DENOPS_AI_MODEL", "gpt-6-sol"),
        max_output_tokens=max_output_tokens,
    )
