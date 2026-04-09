from typing import Annotated, Literal, NotRequired, TypedDict

from langgraph.graph import StateGraph, START, END

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from dotenv import load_dotenv

from agents.roles.judge import Judge
from agents.roles.writer import Writer
from agents.roles.researcher import Researcher

# --- SETUP ---
load_dotenv()

# --- EVERYTHING SHARED BY THE AI AGENTS ---
class SharedState(TypedDict):
    decision: bool
    messages: Annotated[list[BaseMessage], add_messages]
    installation_id: int
    repo_name: str
    base_sha: str
    head_sha: str
    research_notes: NotRequired[str]
    writer_attempts: NotRequired[int]

# --- PLAYGROUND ---
MAX_WRITER_ATTEMPTS = 5

researcher = Researcher()
judge = Judge()
writer = Writer()


def route_after_judge(state: SharedState) -> Literal["passed", "failed", "max_attempts"]:
    if state["decision"]:
        return "passed"
    if state.get("writer_attempts", 0) >= MAX_WRITER_ATTEMPTS:
        print(
            f"[workflow] Max writer attempts ({MAX_WRITER_ATTEMPTS}) reached; "
            "ending with the latest Writer Generation draft."
        )
        return "max_attempts"
    return "failed"


# --- GRAPH ---
workflow = StateGraph(SharedState)

# --- NODES ---
workflow.add_node('researcher', researcher.run)
workflow.add_node('writer', writer.run)
workflow.add_node('judge', judge.run)

# --- FLOW ---
workflow.add_edge(START, 'researcher')
workflow.add_edge('researcher', 'writer')

# Writing Loop: Writer <-> Judge
workflow.add_edge('writer', 'judge')
workflow.add_conditional_edges(
    "judge",
    route_after_judge,
    {
        "passed": END,
        "failed": "writer",
        "max_attempts": END,
    },
)

# --- COMPILATION (this graph variable is used in main to use) ---
graph=workflow.compile()

# --- INVOKING (done on main.py, sample run mentioned because I get confused with formats)---
# app.invoke({
#     'decision': False,
#     'attempts': 0, # Add this to your State if you want to use your 'router' logic
#     'messages': [HumanMessage(content="New push detected. Please update the README.")],
#     'installation_id': 1234567, 
#     'repo_name': "your/repo",
#     'base_sha': "abc...",
#     'head_sha': "xyz..."
# })
