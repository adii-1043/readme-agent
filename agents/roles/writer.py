from agents.base.base_agent import BaseAgent
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.console_sections import print_section
from agents.llm_parser import bind_output_tokens, sanitize_readme_draft, string_from_llm_content
from agents.llms import WRITER_MODEL

WRITER_PROMPT = """
You are the README writer for a GitHub repository.

Write a polished, accurate, publishable README in Markdown using only the information provided in the conversation and repo context.
If the conversation includes an existing README, revise and improve it rather than rewriting blindly.
If the conversation includes judge feedback, treat the most recent feedback as required and fix those issues in the next draft.

Priorities, in order:
1. Accuracy to the codebase and supplied context
2. Clear explanation of what the project does and why it exists
3. Practical setup, usage, and configuration guidance
4. Strong organization and readable Markdown

Rules:
- Do not invent features, commands, files, environment variables, URLs, badges, metrics, or examples that are not supported by the context.
- If context is incomplete, stay truthful and keep unsupported details out.
- Prefer concrete, user-helpful sections such as overview, features, setup, usage, project structure, and contribution notes when the evidence supports them.
- Keep wording crisp and developer-friendly.

Output only the final README Markdown with no preamble, explanation, or code fences around the whole answer.

Never include judge-style lines in the README (for example lines starting with "status:" or "feedback:").
Never repeat the literal prefix "Writer Generation:" in your output.
"""

class Writer(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Writer",
            description=WRITER_PROMPT,
            model=WRITER_MODEL
        )

    def run(self, state):
        attempt = state.get("writer_attempts", 0) + 1
        message_stream = [
            SystemMessage(content=WRITER_PROMPT),
            *state['messages']
        ]
        bound = bind_output_tokens(self.model, 3500)
        raw = string_from_llm_content(bound.invoke(message_stream).content)
        response = sanitize_readme_draft(raw)

        # Occasional provider hiccup: empty output. Retry once with an explicit instruction.
        if not response.strip():
            print(f"[Writer] attempt {attempt}: empty output; retrying once")
            retry_stream = [
                *message_stream,
                HumanMessage(
                    content=(
                        "Your previous output was empty. Output ONLY the README Markdown now. "
                        "Do not include any preamble, notes, or judge-style lines."
                    )
                ),
            ]
            raw = string_from_llm_content(bound.invoke(retry_stream).content)
            response = sanitize_readme_draft(raw)

        # If the model still adds a "Note:" style line at the end, strip it.
        # (We keep this conservative: remove only a trailing single-line note.)
        lines = response.splitlines()
        if lines and lines[-1].lstrip().lower().startswith(("note:", "notes:")):
            response = "\n".join(lines[:-1]).rstrip()

        if not response:
            print(f"[Writer] attempt {attempt}: empty model output (raw type={type(raw)!r})")
        print_section(f"Writer — README draft (attempt {attempt})", response or "(empty)")
        return {
            "writer_attempts": attempt,
            "messages": [AIMessage(content=f"Writer Generation: {response}")]
        }
