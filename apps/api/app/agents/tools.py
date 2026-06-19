"""Coder tool definitions and sandbox executor.

This module owns two things:

1. ``CODER_TOOLS`` — the list of ``genai_types.Tool`` objects passed to
   ``GenerateContentConfig(tools=CODER_TOOLS)``.  These are the function
   declarations the Gemini model sees and can invoke.

2. ``execute_tool`` — the async dispatcher that receives a function name +
   args from the model's response and executes the real operation against a
   live e2b sandbox instance, returning a JSON-serialisable result dict that
   becomes the ``FunctionResponse.response``.

Tool descriptions are the literal documentation the model reads when deciding
which tool to call — keep them precise and action-oriented.
"""

from __future__ import annotations

from typing import Any

from e2b import AsyncSandbox
from google.genai import types as genai_types

# ---------------------------------------------------------------------------
# Tool definitions (FunctionDeclarations sent to Gemini)
# ---------------------------------------------------------------------------

_read_file = genai_types.FunctionDeclaration(
    name="read_file",
    description=(
        "Read the complete contents of a file in the sandbox. "
        "Always read a file before editing it so you can make targeted changes "
        "rather than overwriting content you haven't seen."
    ),
    parameters=genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "path": genai_types.Schema(
                type=genai_types.Type.STRING,
                description="Absolute path to the file to read.",
            ),
        },
        required=["path"],
    ),
)

_write_file = genai_types.FunctionDeclaration(
    name="write_file",
    description=(
        "Overwrite a file in the sandbox with the given content. "
        "Creates the file (and any missing parent directories) if it does not "
        "exist. Write the *complete* new file contents — partial writes are not "
        "supported."
    ),
    parameters=genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "path": genai_types.Schema(
                type=genai_types.Type.STRING,
                description="Absolute path to the file to write.",
            ),
            "content": genai_types.Schema(
                type=genai_types.Type.STRING,
                description="Full new content for the file.",
            ),
        },
        required=["path", "content"],
    ),
)

_list_files = genai_types.FunctionDeclaration(
    name="list_files",
    description=(
        "List the files and subdirectories inside a directory in the sandbox. "
        "Use this to explore the repository layout before deciding which files "
        "to read or edit."
    ),
    parameters=genai_types.Schema(
        type=genai_types.Type.OBJECT,
        properties={
            "directory": genai_types.Schema(
                type=genai_types.Type.STRING,
                description="Absolute path to the directory to list.",
            ),
        },
        required=["directory"],
    ),
)

# Single Tool object to pass to GenerateContentConfig.
CODER_TOOLS: list[genai_types.Tool] = [
    genai_types.Tool(function_declarations=[_read_file, _write_file, _list_files])
]


# ---------------------------------------------------------------------------
# Sandbox executor
# ---------------------------------------------------------------------------


async def execute_tool(
    sandbox: AsyncSandbox,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch a Gemini function call to the live e2b sandbox.

    Args:
        sandbox: Live ``AsyncSandbox`` instance with the cloned repo inside.
        name:    ``part.function_call.name`` from the Gemini response.
        args:    ``part.function_call.args`` — a plain dict of arguments.

    Returns:
        A JSON-serialisable dict that becomes ``FunctionResponse.response``.
        On tool errors the dict contains an ``"error"`` key rather than
        raising — the model receives the error text and can decide how to
        proceed.
    """
    if name == "read_file":
        path: str = args.get("path", "")
        try:
            content = await sandbox.files.read(path)
            return {"content": content}
        except Exception as exc:
            return {"error": str(exc)}

    if name == "write_file":
        path = args.get("path", "")
        content_str: str = args.get("content", "")
        try:
            # Ensure parent directories exist
            parent = "/".join(path.split("/")[:-1])
            if parent:
                await sandbox.commands.run(f"mkdir -p {parent}", timeout=10)
            await sandbox.files.write(path, content_str)
            return {"success": True}
        except Exception as exc:
            return {"error": str(exc)}

    if name == "list_files":
        directory: str = args.get("directory", "")
        try:
            entries = await sandbox.files.list(directory)
            return {
                "entries": [
                    {
                        "name": e.name,
                        "type": e.type.value if e.type else "unknown",
                    }
                    for e in entries
                ]
            }
        except Exception as exc:
            return {"error": str(exc)}

    return {"error": f"Unknown tool: {name!r}"}
