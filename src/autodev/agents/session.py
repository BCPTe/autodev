"""Runs one agent conversation, interactively when the run has a `RunControl`, one-shot otherwise."""
from dataclasses import replace
from typing import Callable

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, Message, ResultMessage, query

from autodev.control import current_control


def _finished(result: ResultMessage | None) -> bool:
    return result is not None and not result.is_error and result.structured_output is not None


async def run_session(prompt: str, options: ClaudeAgentOptions, on_message: Callable[[Message], None]) -> ResultMessage:
    control = current_control.get()
    if control is None:
        async for message in query(prompt=prompt, options=options):
            on_message(message)
            if isinstance(message, ResultMessage):
                return message
        raise RuntimeError("agent produced no result")

    control.cwd = str(options.cwd or "/")
    options = replace(options, can_use_tool=control.can_use_tool, permission_mode="default")
    async with ClaudeSDKClient(options) as client:
        control.client = client
        try:
            await client.query(prompt)
            while True:
                result: ResultMessage | None = None
                async for message in client.receive_response():
                    on_message(message)
                    if isinstance(message, AssistantMessage):
                        control.narrate(message)
                    if isinstance(message, ResultMessage):
                        result = message
                if _finished(result):
                    control.drop_pending()
                    return result  # type: ignore[return-value]
                if control.take_interrupt():
                    await client.query(await control.next_instruction())
                    continue
                if result is None:
                    raise RuntimeError("agent produced no result")
                return result
        finally:
            control.client = None
