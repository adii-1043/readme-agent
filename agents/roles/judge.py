from agents.base.base_agent import BaseAgent
from langchain_core.messages import SystemMessage, HumanMessage

from agents.console_sections import print_section
from agents.llm_parser import bind_output_tokens, parse_judge_status, string_from_llm_content
from agents.llms import JUDGE_MODEL

JUDGE_PROMPT = """
You are a strict reviewer for GitHub README drafts.

How to read the conversation:
- The researcher's thesis and grounded facts appear in the message whose content starts with "Researcher Notes:" (and may be echoed in the structured research_notes field if present). Treat that as the source of truth about the repo; do not demand details that were never researched.
- The README draft you are grading is always the latest assistant message whose content starts with "Writer Generation:". Older "Writer Generation:" messages are prior drafts; ignore them except to see what changed.
- "Judge Feedback:" messages are your own prior rounds; use them to see whether the writer addressed recurring issues.

Review that latest draft against the researcher notes and prior feedback.
Judge the draft on factual accuracy, coverage of the important project details, usability of setup and usage instructions, structure, clarity, and whether it avoids unsupported claims.
Only mark the README as approved if it is genuinely ready to publish without any meaningful factual or clarity issues.

You must respond in exactly this format (two lines only, no other text before or after):
status: approved
feedback: <3-4 sentences for the writer>

or

status: disapproved
feedback: <3-4 sentences for the writer>

Do not paste or repeat the README draft in your response. Do not use markdown headers, code fences, or timestamps in your response.

Rules for feedback:
- Be specific about what is missing, unclear, misleading, or strong.
- Mention the highest-impact fixes first.
- Do not use the word "approved" in the feedback text.
- Do not add any extra sections or lines.
"""

class Judge(BaseAgent):
    def __init__(self):
        super().__init__(
            name="Judge",
            description=JUDGE_PROMPT,
            model=JUDGE_MODEL
        )

    def run(self, state):
        research = (state.get("research_notes") or "").strip()
        anchor = HumanMessage(
            content=(
                "Authoritative research summary (state `research_notes`, same text as "
                '"Researcher Notes:" in the thread):\n\n'
                f"{research if research else '(missing — use the Researcher Notes message in the thread.)'}"
            )
        )
        messages = [SystemMessage(content=self.description), anchor, *state["messages"]]

        # Provider can occasionally return empty output; retry once with a stricter reminder.
        bound = bind_output_tokens(self.model, 250)
        response = string_from_llm_content(bound.invoke(messages).content)
        decision, _ = parse_judge_status(response)
        if (not response.strip()) or (
            not any(line.strip().lower().startswith("status:") for line in response.splitlines())
        ):
            print("[Judge] empty/malformed output; retrying once")
            retry_messages = [
                *messages,
                HumanMessage(
                    content=(
                        "Return ONLY two lines in plain text:\n"
                        "status: approved|disapproved\n"
                        "feedback: <3-4 sentences>\n"
                        "No other text."
                    )
                ),
            ]
            response = string_from_llm_content(bound.invoke(retry_messages).content)
            decision, _ = parse_judge_status(response)

        after_attempt = state.get("writer_attempts", 0)
        verdict = "APPROVED" if decision else "NOT APPROVED (send back to writer or stop at cap)"
        judge_block = (
            f"After writer attempt: {after_attempt}\n"
            f"Verdict: {verdict}\n\n"
            f"Full judge output:\n{response}"
        )
        print_section("Judge — review", judge_block)

        return {
            "decision": decision,
            "messages": [HumanMessage(content=f"Judge Feedback: {response}")]
        }
