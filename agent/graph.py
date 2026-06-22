# agent/graph.py
import os
import re
import logging
from typing import Annotated, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from tools import execute_sql, get_sample_data
from prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

# ─── Tools ───────────────────────────────────────────────────────────────────
tools     = [execute_sql, get_sample_data]
tool_node = ToolNode(tools)

# ─── LLM ─────────────────────────────────────────────────────────────────────
llm = ChatOpenAI(
    model=os.getenv("MODEL_NAME", "qwen2.5:3b"),
    base_url=os.getenv("OPENAI_BASE_URL", "http://host.docker.internal:11434/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "ollama"),
    temperature=0,
).bind_tools(tools)


# ─── State ───────────────────────────────────────────────────────────────────
class AgentState(TypedDict):
    messages:      Annotated[list[BaseMessage], add_messages]
    generated_sql: str | None
    retry_count:   int


# ─── Extract SQL از متن پاسخ ─────────────────────────────────────────────────
def extract_sql_from_text(text: str) -> str | None:
    """
    اگر مدل SQL رو توی متن نوشت ولی execute نکرد،
    اینجا SQL رو استخراج می‌کنیم
    """
    # پیدا کردن SQL بین backtick
    patterns = [
        r"```sql\n(.*?)```",
        r"```\n(SELECT.*?)```",
        r"(SELECT\s+.*?;)",
        r"(SELECT\s+.*?)(?:\n\n|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            sql = match.group(1).strip()
            if sql.upper().startswith("SELECT"):
                return sql
    return None


# ─── Nodes ───────────────────────────────────────────────────────────────────
def call_model(state: AgentState) -> AgentState:
    messages  = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response  = llm.invoke(messages)

    # استخراج SQL از tool_calls
    generated_sql = state.get("generated_sql")
    if hasattr(response, "tool_calls") and response.tool_calls:
        for tc in response.tool_calls:
            if tc["name"] == "execute_sql":
                generated_sql = tc["args"].get("query", generated_sql)

    log.info(f"🤖 Response: {response.content[:150] if response.content else 'tool_call'}")
    log.info(f"🔧 Tool calls: {response.tool_calls if hasattr(response, 'tool_calls') else 'none'}")

    return {
        "messages":      [response],
        "generated_sql": generated_sql,
        "retry_count":   state.get("retry_count", 0),
    }


def force_execute(state: AgentState) -> AgentState:
    """
    اگر مدل SQL نوشت ولی execute نکرد،
    ما خودمون SQL رو استخراج و اجرا می‌کنیم
    """
    last_message  = state["messages"][-1]
    text          = last_message.content if hasattr(last_message, "content") else ""
    sql           = extract_sql_from_text(text)

    if sql:
        log.info(f"🔄 Force executing SQL: {sql}")

        # اجرای مستقیم SQL
        result = execute_sql.invoke({"query": sql})

        # ساخت پیام جدید با نتیجه
        new_message = AIMessage(
            content=f"کوئری اجرا شد. نتیجه:\n{result}\n\nبر اساس نتیجه، پاسخ سوال شما را می‌دهم."
        )

        return {
            "messages":      [new_message],
            "generated_sql": sql,
            "retry_count":   state.get("retry_count", 0) + 1,
        }

    return {
        "messages":      [],
        "generated_sql": state.get("generated_sql"),
        "retry_count":   state.get("retry_count", 0) + 1,
    }


def generate_final_answer(state: AgentState) -> AgentState:
    """
    بعد از force_execute، از مدل می‌خوایم
    پاسخ نهایی فارسی رو بده
    """
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    messages.append(HumanMessage(content="حالا بر اساس نتیجه کوئری، پاسخ را به فارسی روان توضیح بده."))
    response = llm.invoke(messages)

    log.info(f"✅ Final answer: {response.content[:150]}")

    return {
        "messages":      [response],
        "generated_sql": state.get("generated_sql"),
        "retry_count":   state.get("retry_count", 0),
    }


# ─── Conditions ──────────────────────────────────────────────────────────────
def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]

    # اگر tool call داره → برو tools
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"

    # اگر متن داره و SQL توش هست ولی execute نکرده
    if hasattr(last, "content") and last.content:
        sql = extract_sql_from_text(last.content)
        retry = state.get("retry_count", 0)
        if sql and retry < 2:
            log.info("⚠️ Model wrote SQL but didn't execute → forcing execution")
            return "force_execute"

    return END


def after_force_execute(state: AgentState) -> str:
    """بعد از force execute، پاسخ نهایی رو بگیر"""
    return "final_answer"


# ─── Build Graph ─────────────────────────────────────────────────────────────
def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("agent",         call_model)
    graph.add_node("tools",         tool_node)
    graph.add_node("force_execute", force_execute)
    graph.add_node("final_answer",  generate_final_answer)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools":         "tools",
            "force_execute": "force_execute",
            END:              END,
        }
    )

    graph.add_edge("tools",         "agent")
    graph.add_edge("force_execute", "final_answer")
    graph.add_edge("final_answer",  END)

    return graph.compile()


agent_graph = build_graph()


# ─── Public API ──────────────────────────────────────────────────────────────
async def run_agent(question: str, history: list = None) -> dict:
    messages = []

    if history:
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                messages.append(AIMessage(content=msg["content"]))

    messages.append(HumanMessage(content=question))

    result = await agent_graph.ainvoke({
        "messages":      messages,
        "generated_sql": None,
        "retry_count":   0,
    })

    final = result["messages"][-1]

    return {
        "answer": final.content,
        "sql":    result.get("generated_sql"),
    }