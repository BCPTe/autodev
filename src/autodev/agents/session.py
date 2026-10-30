"""Runs one agent conversation, interactively when the run has a `RunControl`, one-shot otherwise."""
import asyncio
from contextlib import aclosing
from dataclasses import replace
from typing import Callable

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, Message, ResultMessage, query

from autodev.agents.usage import Meter, from_result, record
from autodev.control import current_control

NO_MEMORY_ENV = {"CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}
STREAM_END_TIMEOUT = 5.0


def isolation(user_mcp: bool = False) -> dict:
    """Options that keep the user's own Claude setup out of an unattended session.

    Without them the CLI attaches every MCP server and connector of the logged-in account (tens of
    thousands of tokens of tool definitions that each turn re-reads from the cache) and the user's
    personal memory of the project, none of which the agent can or should use.
    """
    return {"strict_mcp_config": not user_mcp, "env": dict(NO_MEMORY_ENV)}


def _finished(result: ResultMessage | None) -> bool:
    return result is not None and not result.is_error and result.structured_output is not None


async def run_session(prompt: str, options: ClaudeAgentOptions, on_message: Callable[[Message], None], stage: str = "agent") -> ResultMessage:
    meter = Meter()

    def tap(message: Message) -> None:
        meter.feed(message)
        on_message(message)

    result = await _converse(prompt, options, tap)
    record(from_result(stage, options.model or "", result, meter, resumed=bool(options.resume)))
    return result


async def _drain(stream) -> None:
    async for _ in stream:
        pass


async def _converse(prompt: str, options: ClaudeAgentOptions, on_message: Callable[[Message], None]) -> ResultMessage:
    control = current_control.get()
    if control is None:
        # Let the stream reach its end after the result, so the SDK reaps the CLI process before the loop
        # closes; give up after a few seconds (it can hang) and close it here, in this task, either way.
        async with aclosing(query(prompt=prompt, options=options)) as stream:
            async for message in stream:
                on_message(message)
                if isinstance(message, ResultMessage):
                    try:
                        await asyncio.wait_for(_drain(stream), STREAM_END_TIMEOUT)
                    except TimeoutError:
                        pass
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
