"""System prompt builder. Rebuilt fresh per intent."""
from __future__ import annotations

from textwrap import dedent

RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "thinking": {"type": "string", "maxLength": 1000,
                     "description": "Private reasoning, not shown to the user. Be concise."},
        "action": {"type": "string", "enum": ["tool_call", "clarify", "finish"]},
        "tool": {"type": ["string", "null"]},
        "arguments": {"type": ["object", "null"]},
        "question": {"type": ["string", "null"]},
        "user_message": {"type": ["string", "null"]},
        "summary": {"type": ["string", "null"]},
    },
    "required": ["thinking", "action"],
    "additionalProperties": False,
}

# Hard ceiling for thinking field, applied Python-side as defense in depth in case
# the inference engine doesn't honor maxLength. Truncated content is replaced with
# a marker; the loop logs a WARNING.
THINKING_HARD_CAP_CHARS = 2000

_PREAMBLE = dedent("""\
    You are a Maya animation assistant working inside the user's Maya session.
    You accomplish tasks by calling tools. You never write or generate Maya code
    directly - you only choose tools from the inventory below.

    ## Response format
    Every response is one JSON object:
    - thinking: short private reasoning, the user does not see this. Keep under ~200 words.
    - action: "tool_call" | "clarify" | "finish"

    For action="tool_call":
      tool: string (name from inventory)
      arguments: object matching that tool's argument schema

    For action="clarify":
      question: the question to ask the user

    For action="finish":
      user_message: what the user sees as your reply
      summary: <=3 sentences capturing what was done. **Be structural, not narrative.** This
        is the memory used by future intents (e.g., "now do the same for the legs"). Future-you
        needs to mechanically copy the structure. Use this format:

          "Called <tool>(<key_args_compactly>) [<count>x if repeated]. Result: <outcome>."

        Examples (good - structural):
          - "Called fix_euler_discontinuities(objects=[rig:L_arm_FK_CTL, rig:L_arm_FK_2,
             rig:L_arm_FK_3]). Fixed 7 discontinuities across rotateY."
          - "Called inspect_scene(deep=true). Found 12 controls in rig: namespace; no mutations."
          - "Called playblast(output_path='/tmp/shot_010', start=1, end=120). Wrote
             /tmp/shot_010.mov."

        Counter-examples (bad - narrative, do NOT do this):
          - "I cleaned up the arm controls successfully."  <- which arms? which controls?
          - "Did the playblast you asked for."             <- which params? where did it go?

    ## Decision policy
    - Prefer to act on the most likely interpretation; explain assumptions in your final user_message.
    - Use clarify only when guessing wrong would mutate the scene in a way expensive to revert.
    - You may clarify at most {max_clarifies} times per intent.
    - After a tool returns an error, read it carefully before retrying - most errors are caused by wrong arguments, not missing capability.
    - Tools that take a list of targets (e.g., `objects: list[str]`) should be called with the **full list**, not one target per call. Batching keeps the step budget honest.
""")


def _render_inventory(inventory: list[dict]) -> str:
    """Compact, line-per-arg rendering of the tool inventory."""
    lines: list[str] = []
    for entry in inventory:
        lines.append(f"- name: {entry['name']}")
        lines.append(f"  mutating: {str(entry['mutating']).lower()}")
        lines.append(f"  description: {entry['description'].strip()}")
        schema = entry.get("json_schema") or {}
        props = schema.get("properties") or {}
        required = set(schema.get("required") or [])
        if props:
            lines.append("  arguments:")
            for arg_name, arg_schema in props.items():
                t = arg_schema.get("type", "any")
                desc = arg_schema.get("description", "")
                default = arg_schema.get("default")
                req_marker = "*" if arg_name in required else ""
                if default is not None:
                    arg_line = f"    {arg_name}{req_marker}: {t} = {default!r}"
                else:
                    arg_line = f"    {arg_name}{req_marker}: {t}"
                if desc:
                    arg_line += f"   -- {desc}"
                lines.append(arg_line)
        else:
            lines.append("  arguments: (none)")
    return "\n".join(lines)


def _render_summaries(summaries: list[tuple[str, str]]) -> str:
    if not summaries:
        return "(no previous intents)"
    out = []
    for user_text, summary in summaries:
        out.append(f"- intent: {user_text!r}")
        out.append(f"  result: {summary}")
    return "\n".join(out)


def build_system_prompt(
    inventory: list[dict],
    *,
    max_clarifies: int,
    summaries: list[tuple[str, str]],
    current_intent: str,
) -> str:
    return (
        _PREAMBLE.format(max_clarifies=max_clarifies)
        + "\n## Tool inventory\n"
        + _render_inventory(inventory)
        + "\n\n## Memory of previous intents\n"
        + _render_summaries(summaries)
        + "\n\n## Current intent\n"
        + current_intent.strip()
        + "\n"
    )
