"""
Copilot orchestration with LangGraph.

Graph (one run per user message):

  plan -> discover_tools -> resolve_scope --(no scope)--------------------------> compose_answer
                                          \\-(MCP down)-> retrieve_documents ----> compose_answer
                                          \\-> fetch_alarms -> analyze_alarms -> prioritize_and_recommend
                                                -> asset_context -> retrieve_documents -> compose_answer

Every MCP call goes through the McpToolbox (apps/backend/mcp_client.py),
which records the call in the execution trace shown in the GUI.
"""

import operator
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from apps.backend import answer
from apps.backend.mcp_client import open_toolbox
from apps.backend.planner import make_plan
from rag.retrieval.retriever import DocumentRetriever, keywords

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

_retriever = None


def get_retriever() -> DocumentRetriever:
    global _retriever
    if _retriever is None:
        _retriever = DocumentRetriever()
    return _retriever


# =========================
# State
# =========================


class CopilotState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]  # whole conversation (kept between turns)
    context: dict  # what we remember for follow-up questions (kept between turns)
    question: str
    plan: dict
    tools: list
    assets: list
    alarms: list
    candidate_alarms: list
    focus_alarm: dict | None
    metadata: dict | None
    summary: dict | None
    trends: dict | None
    correlation: dict | None
    priorities: list
    recommendations: dict | None
    documents: dict | None
    refs: dict  # tool name -> trace reference, e.g. {"get_alarms": "T3"}
    warnings: list
    result: dict


def get_toolbox(config: RunnableConfig):
    return config["configurable"].get("toolbox")


def ref_of(toolbox, tool_name: str) -> str | None:
    """Reference of the LAST successful call of a tool, e.g. 'T4'."""
    for step in reversed(toolbox.trace if toolbox else []):
        if step["tool"] == tool_name and step.get("status") == "success":
            return f"T{step['step']}"
    return None


# =========================
# Nodes
# =========================


def plan_node(state: CopilotState):
    plan = make_plan(state["question"], state.get("context") or {})
    return {"plan": plan, "warnings": list(plan["assumptions"])}


async def discover_tools_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    if toolbox is None:
        return {
            "tools": [],
            "warnings": state["warnings"]
            + ["MCP server is unavailable - alarm data could not be loaded. Showing document guidance only."],
        }
    tools = await toolbox.discover()
    return {"tools": [{"name": t["name"], "description": t["description"]} for t in tools]}


async def resolve_scope_node(state: CopilotState, config: RunnableConfig):
    """Turn the asset name in the question into asset ids (via the search_assets MCP tool)."""
    toolbox = get_toolbox(config)
    plan = state["plan"]
    warnings = list(state["warnings"])

    if toolbox is None or plan["off_topic"]:
        return {"assets": []}

    if plan["use_context_assets"]:
        return {"assets": state["context"]["assets"]}

    if not plan["asset_query"] and plan["alarm_id"] and not plan["site"] and not plan["unit"]:
        # Only an alarm id was given ("Investigate ALM-000123"): the alarm tells us the asset
        detail = await toolbox.call(
            "get_alarm_details", {"alarm_id": plan["alarm_id"]}, purpose=f"Find the asset of {plan['alarm_id']}"
        )
        if not detail:
            warnings.append(f"Alarm {plan['alarm_id']} was not found.")
            return {"assets": [], "warnings": warnings}
        alarm = detail["alarm"]
        asset = {
            "asset_id": alarm["asset_id"],
            "asset_name": alarm["asset_name"],
            "asset_type": "unknown",  # filled in later from get_asset_metadata
            "site": alarm["site"],
            "unit": alarm["unit"],
        }
        return {"assets": [asset], "warnings": warnings}

    if not plan["asset_query"]:
        return {"assets": []}

    data = await toolbox.call(
        "search_assets",
        {"query": plan["asset_query"], "site": plan["site"], "unit": plan["unit"], "limit": 5},
        purpose=f"Resolve '{plan['asset_query']}' to an asset id",
    )
    if not data or not data["results"]:
        warnings.append(f"No asset matched '{plan['asset_query']}'. Please check the asset name.")
        return {"assets": [], "warnings": warnings}

    results = data["results"]
    specific = any(ch.isdigit() for ch in plan["asset_query"])
    if specific:
        if results[0]["match_score"] < 0.75:
            closest = ", ".join(r["asset_name"] for r in results[:3])
            warnings.append(f"No asset exactly matches '{plan['asset_query']}'. Closest matches: {closest}.")
            return {"assets": [], "warnings": warnings}
        chosen = [results[0]]
    else:
        best = results[0]["match_score"]
        chosen = [r for r in results if r["match_score"] == best][:3]
        if len(chosen) > 1:
            warnings.append(
                f"'{plan['asset_query']}' matched several assets - looking at: "
                + ", ".join(r["asset_name"] for r in chosen)
                + "."
            )

    assets = [
        {
            "asset_id": r["asset_id"],
            "asset_name": r["asset_name"],
            "asset_type": r["asset_type"],
            "site": r["site"],
            "unit": r["unit"],
        }
        for r in chosen
    ]
    return {"assets": assets, "warnings": warnings}


def route_after_scope(state: CopilotState, config: RunnableConfig):
    if get_toolbox(config) is None:
        return "retrieve_documents"
    plan = state["plan"]
    if state["assets"] or plan["site"] or plan["unit"]:
        return "fetch_alarms"
    return "compose_answer"


def pick_focus_name(question: str, alarms: list[dict]) -> str | None:
    """If the question mentions an alarm type ('motor trip', 'discharge pressure'), focus on it."""
    question_words = keywords(question)
    best_name, best_score = None, 0.0
    for name in {a["alarm_name"] for a in alarms}:
        name_words = keywords(name)
        score = len(name_words & question_words) / len(name_words) if name_words else 0
        if score > best_score:
            best_name, best_score = name, score
    return best_name if best_score >= 0.5 else None


def most_important(alarms: list[dict]) -> dict | None:
    if not alarms:
        return None
    return max(alarms, key=lambda a: (a["status"] == "active", SEVERITY_RANK[a["severity"]], a["start_time"]))


async def fetch_alarms_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    plan = state["plan"]
    warnings = list(state["warnings"])
    common = {
        "status": plan["status"],
        "severity": plan["severity"],
        "start_time": plan["start_time"],
        "end_time": plan["end_time"],
        "page_size": 100,
        "fetch_all_pages": True,
    }

    alarms = []
    if state["assets"]:
        for asset in state["assets"]:
            data = await toolbox.call(
                "get_alarms", {"asset_id": asset["asset_id"], **common}, purpose=f"Alarms for {asset['asset_name']}"
            )
            if data:
                alarms.extend(data["alarms"])
                if data["pagination"].get("truncated"):
                    warnings.append(f"Alarm list for {asset['asset_name']} was cut at 5 pages.")
    else:
        data = await toolbox.call(
            "get_alarms",
            {"site": plan["site"], "unit": plan["unit"], **common},
            purpose=f"Alarms for {plan['site'] or plan['unit']}",
        )
        if data:
            alarms = data["alarms"]
            if data["pagination"].get("truncated"):
                warnings.append(f"Alarm list for {plan['site'] or plan['unit']} was cut at 5 pages.")

    if not alarms:
        what = "active " if plan["status"] == "active" else ""
        warnings.append(f"No {what}alarms found for this scope in the last {plan['days']} days.")

    focus_name = pick_focus_name(plan["message"], alarms)
    candidates = [a for a in alarms if a["alarm_name"] == focus_name] if focus_name else alarms

    focus = None
    if plan.get("alarm_id"):
        focus = next((a for a in alarms if a["alarm_id"] == plan["alarm_id"]), None)
    if focus is None:
        focus = most_important(candidates)

    assets = state["assets"]
    if focus and len(assets) > 1:
        # several assets matched a generic word ("compressor"): continue with the one that has the focus alarm
        assets = [a for a in assets if a["asset_id"] == focus["asset_id"]]
        alarms = [a for a in alarms if a["asset_id"] == focus["asset_id"]]
        candidates = [a for a in candidates if a["asset_id"] == focus["asset_id"]]
        warnings.append(f"Focusing on {focus['asset_name']} because it has the most important matching alarm.")

    return {
        "alarms": alarms,
        "candidate_alarms": candidates,
        "focus_alarm": focus,
        "assets": assets,
        "warnings": warnings,
    }


async def asset_context_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    if "metadata" not in state["plan"]["steps"]:
        return {}
    asset_id = (
        state["assets"][0]["asset_id"]
        if state["assets"]
        else (state["focus_alarm"]["asset_id"] if state["focus_alarm"] else None)
    )
    if not asset_id:
        return {}
    data = await toolbox.call("get_asset_metadata", {"asset_id": asset_id}, purpose="Asset details and related assets")
    return {"metadata": data}


async def analyze_alarms_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    plan = state["plan"]
    steps = plan["steps"]
    asset_ids = [a["asset_id"] for a in state["assets"]] or None
    scope = {
        "asset_ids": asset_ids,
        "site": None if asset_ids else plan["site"],
        "unit": None if asset_ids else plan["unit"],
        "start_time": plan["start_time"],
        "end_time": plan["end_time"],
    }
    updates = {}

    if "summary" in steps:
        updates["summary"] = await toolbox.call(
            "get_alarm_summary",
            {
                **scope,
                "severity": plan["severity"],
                "group_by": ["alarm_name"],
                "kpis": ["alarm_count", "recurring_rate", "avg_ack_delay", "critical_count", "active_count"],
            },
            purpose="Recurring alarm statistics",
        )

    if "trends" in steps:
        updates["trends"] = await toolbox.call(
            "get_alarm_trends",
            {**scope, "severity": plan["severity"], "bucket": "weekly"},
            purpose="Is the alarm rate going up or down?",
        )

    if "correlation" in steps:
        ids = asset_ids or ([state["focus_alarm"]["asset_id"]] if state["focus_alarm"] else None)
        if ids:
            updates["correlation"] = await toolbox.call(
                "correlate_alarms",
                {
                    "asset_ids": ids,
                    "start_time": plan["start_time"],
                    "end_time": plan["end_time"],
                    "lag_window_minutes": 15,
                    "severity_threshold": "medium",
                    "min_support": 2,
                },
                purpose="Which alarms happen together (likely causes)",
            )
    return updates


async def prioritize_and_recommend_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    plan = state["plan"]
    focus = state["focus_alarm"]
    priorities = []

    if "priority" in plan["steps"] and state["candidate_alarms"]:
        if plan["intent"] == "highest_priority":
            # score several active alarms and pick the highest
            to_score = sorted(
                state["candidate_alarms"], key=lambda a: (-SEVERITY_RANK[a["severity"]], a["start_time"])
            )[:8]
        else:
            to_score = [focus] if focus else []
        for alarm in to_score:
            score = await toolbox.call(
                "score_alarm_priority", {"alarm_id": alarm["alarm_id"]}, purpose=f"Priority of {alarm['alarm_id']}"
            )
            if score:
                priorities.append(score)
        if priorities and plan["intent"] == "highest_priority":
            best = max(priorities, key=lambda p: p["priority_score"])
            focus = next(a for a in state["candidate_alarms"] if a["alarm_id"] == best["alarm_id"])

    recommendations = None
    if "recommendations" in plan["steps"] and focus:
        # output of one tool (alarm id from get_alarms / priority) is the input of the next
        recommendations = await toolbox.call(
            "get_operator_recommendations", {"alarm_id": focus["alarm_id"]}, purpose="API recommended operator actions"
        )
    return {"priorities": priorities, "focus_alarm": focus, "recommendations": recommendations}


RAG_HINTS = {
    "investigation": "recurring likely causes alarm response procedure actions",
    "recurring_causes": "repeated recurring likely causes troubleshooting",
    "active_alarms": "alarm response immediate actions",
    "highest_priority": "alarm response immediate actions",
    "related_assets": "related assets to inspect related equipment",
    "procedure": "operating procedure alarm response",
    "consistency": "alarm response actions restart rule",
}


def retrieve_documents_node(state: CopilotState):
    plan = state["plan"]
    warnings = list(state["warnings"])
    focus = state.get("focus_alarm")
    assets = state.get("assets") or []

    parts = []
    if assets:
        parts.append(assets[0]["asset_name"])
    elif focus:
        parts.append(focus["asset_name"])
    elif plan["asset_query"]:
        parts.append(plan["asset_query"])
    if focus:
        parts.append(focus["alarm_name"])
    parts.append(RAG_HINTS[plan["intent"]])
    parts.append(plan["message"][:300])  # the user's own words also guide the search
    query = " ".join(parts)

    # Filter documents by equipment type: the asset itself + its related assets + general documents
    equipment = set()
    metadata = state.get("metadata")
    if metadata:
        equipment.add(metadata["asset_type"])
        equipment.update(r["asset_type"] for r in metadata["related_assets"])
    elif assets:
        equipment.add(assets[0]["asset_type"])
    equipment = sorted(equipment | {"general"}) if equipment else None

    retriever = get_retriever()
    found = retriever.search(query, top_k=5, equipment_types=equipment)
    if found["status"] != "ok" and equipment:
        warnings.append("Filtered document search was weak - searched all documents instead.")
        found = retriever.search(query, top_k=5)

    if found["status"] == "low_confidence":
        warnings.append(
            f"Document match is weak (best score {found['results'][0]['score']}). "
            "Please verify the guidance with a process engineer."
        )
    elif found["status"] == "no_results":
        warnings.append("No relevant documents were found for this question.")

    for chunk in found["results"]:
        if chunk["injection_removed"]:
            warnings.append(
                f"Suspicious instructions were removed from {chunk['doc_id']} "
                f"('{chunk['section']}'). Document text is treated as data, never as instructions."
            )
    return {"documents": found, "warnings": warnings}


def compose_answer_node(state: CopilotState, config: RunnableConfig):
    toolbox = get_toolbox(config)
    plan = state["plan"]
    warnings = list(state["warnings"])
    focus = state.get("focus_alarm")
    assets = state.get("assets") or []
    documents = answer.number_documents((state.get("documents") or {}).get("results", []))

    # ---- failed / unavailable tool steps become visible warnings ----
    for step in toolbox.trace if toolbox else []:
        if step.get("status") not in ("success", None):
            warnings.append(
                f"Step T{step['step']} {step['tool']} {step['status']}: {step.get('error', '')[:160]} "
                "- the answer uses the remaining evidence."
            )

    clarification = None
    if toolbox is not None and not assets and not plan["site"] and not plan["unit"]:
        clarification = (
            "I can investigate alarms for a specific asset or site. Please name an asset "
            "(for example *Boiler Feed Pump 101*) or a site (for example *EastRefinery*)."
        )
        if len(warnings) > len(plan["assumptions"]):
            clarification = warnings[-1] + "\n\n" + clarification

    # ---- alarm summary panel ----
    alarms = state.get("alarms") or []
    summary = state.get("summary")
    trends = state.get("trends")
    alarm_summary = {
        "days": plan["days"],
        "total_alarms": summary["total_alarms"] if summary else (len(alarms) if alarms else None),
        "active_count": sum(1 for a in alarms if a["status"] == "active"),
        "ref": f" [{ref_of(toolbox, 'get_alarms')}]" if ref_of(toolbox, "get_alarms") else "",
        "top_recurring": (summary or {}).get("groups", [])[:5],
        "summary_ref": f" [{ref_of(toolbox, 'get_alarm_summary')}]" if summary else "",
        "trend_direction": trends["trend_direction"] if trends else None,
        "trend_ref": f" [{ref_of(toolbox, 'get_alarm_trends')}]" if trends else "",
        "trend_series": trends["series"] if trends else [],
    }

    focus_view = None
    if focus:
        focus_view = {**focus, "ref": f" [{ref_of(toolbox, 'get_alarms')}]"}
        score = next((p for p in state.get("priorities") or [] if p["alarm_id"] == focus["alarm_id"]), None)
        if score:
            focus_view.update(
                priority_score=score["priority_score"],
                priority_level=score["priority_level"],
                priority_explanation=score["explanation"],
            )

    # ---- likely causes: measured (API) + documented (RAG) ----
    target_ids = {a["asset_id"] for a in assets} or ({focus["asset_id"]} if focus else set())
    measured = answer.likely_causes_from_correlation(
        state.get("correlation"),
        target_ids,
        focus["alarm_name"] if focus else None,
        ref_of(toolbox, "correlate_alarms"),
    )
    focus_words = keywords(focus["alarm_name"]) if focus else set()
    documented = answer.document_causes(documents, focus_words)
    likely_causes = [{**c, "kind": "measured"} for c in measured] + [{**c, "kind": "documented"} for c in documented]

    # ---- recommendations compared with documents ----
    recs = state.get("recommendations")
    recommendations = answer.compare_with_documents(recs["recommended_actions"], documents) if recs else []
    rec_ref = ref_of(toolbox, "get_operator_recommendations")
    for rec in recommendations:
        rec["api_ref"] = rec_ref
    if any(r["doc_check"] == "conflict" for r in recommendations):
        warnings.append(
            "At least one API recommendation conflicts with the documented procedure - "
            "the procedure should take precedence."
        )

    related = answer.related_assets_to_inspect(
        state.get("metadata"), recs, state.get("correlation"), assets[0]["asset_id"] if assets else None
    )

    headlines = {
        "investigation": "Alarm investigation",
        "recurring_causes": "Why these alarms keep occurring",
        "active_alarms": "Active alarms and immediate actions",
        "highest_priority": "Highest-priority alarm",
        "related_assets": "Related assets to inspect",
        "procedure": "Applicable operating procedure",
        "consistency": "API recommendations vs documented procedures",
    }
    scope_name = ", ".join(a["asset_name"] for a in assets) or plan["site"] or plan["unit"] or plan["asset_query"] or ""

    result = {
        "question": state["question"],
        "intent": plan["intent"],
        "headline": f"{headlines[plan['intent']]}{' - ' + scope_name if scope_name else ''}",
        "clarification": clarification,
        "plan": {
            k: plan[k]
            for k in (
                "intent",
                "asset_query",
                "site",
                "unit",
                "status",
                "severity",
                "days",
                "start_time",
                "end_time",
                "steps",
            )
        },
        "assets": assets,
        "alarm_summary": alarm_summary,
        "alarms_table": sorted(
            state.get("candidate_alarms") or alarms,
            key=lambda a: (a["status"] != "active", -SEVERITY_RANK[a["severity"]]),
        )[:10],
        "focus_alarm": focus_view,
        "priorities": state.get("priorities") or [],
        "likely_causes": likely_causes,
        "recommendations": recommendations,
        "related_assets": related,
        "procedure": answer.pick_procedure(documents),
        "citations": [
            {
                "ref": d["ref"],
                "doc_id": d["doc_id"],
                "title": d["title"],
                "section": d["section"],
                "doc_type": d["doc_type"],
                "score": d["score"],
                "text": d["text"],
                "chunk_id": d["chunk_id"],
                "source_file": d["source_file"],
                "injection_removed": d["injection_removed"],
                "trust_level": d.get("trust_level", "internal"),
            }
            for d in documents
        ],
        "retrieval": {k: (state.get("documents") or {}).get(k) for k in ("query", "filters", "status")},
        "tools": state.get("tools") or [],
        "trace": toolbox.trace if toolbox else [],
        "trace_id": toolbox.trace_id if toolbox else None,
        "warnings": warnings,
    }

    text, llm_error = (None, None)
    if not clarification:
        text, llm_error = answer.llm_answer(result, documents)
    if llm_error:
        result["warnings"].append(llm_error)
    result["answer_source"] = "llm" if text else "template"
    result["answer_markdown"] = text or answer.render_markdown(result)

    # remember the scope for follow-up questions
    context = dict(state.get("context") or {})
    if assets:
        context["assets"] = assets
    if focus:
        context["alarm_id"] = focus["alarm_id"]
        if not assets:
            context["assets"] = [
                {
                    "asset_id": focus["asset_id"],
                    "asset_name": focus["asset_name"],
                    "asset_type": (state.get("metadata") or {}).get("asset_type", "general"),
                    "site": focus["site"],
                    "unit": focus["unit"],
                }
            ]

    return {"result": result, "context": context, "messages": [AIMessage(content=result["answer_markdown"])]}


# =========================
# Build graph
# =========================

graph = StateGraph(CopilotState)

graph.add_node("plan", plan_node)
graph.add_node("discover_tools", discover_tools_node)
graph.add_node("resolve_scope", resolve_scope_node)
graph.add_node("fetch_alarms", fetch_alarms_node)
graph.add_node("asset_context", asset_context_node)
graph.add_node("analyze_alarms", analyze_alarms_node)
graph.add_node("prioritize_and_recommend", prioritize_and_recommend_node)
graph.add_node("retrieve_documents", retrieve_documents_node)
graph.add_node("compose_answer", compose_answer_node)

graph.add_edge(START, "plan")
graph.add_edge("plan", "discover_tools")
graph.add_edge("discover_tools", "resolve_scope")
graph.add_conditional_edges(
    "resolve_scope", route_after_scope, ["fetch_alarms", "retrieve_documents", "compose_answer"]
)
graph.add_edge("fetch_alarms", "analyze_alarms")
graph.add_edge("analyze_alarms", "prioritize_and_recommend")
graph.add_edge("prioritize_and_recommend", "asset_context")
graph.add_edge("asset_context", "retrieve_documents")
graph.add_edge("retrieve_documents", "compose_answer")
graph.add_edge("compose_answer", END)

# Conversation memory per thread_id (in-process). Swap for a Postgres saver in production.
checkpointer = MemorySaver()
copilot_graph = graph.compile(checkpointer=checkpointer)


# =========================
# Entry point used by FastAPI
# =========================


def fresh_turn_state(message: str) -> dict:
    """Per-question fields are reset every turn; messages + context are kept by the checkpointer."""
    return {
        "messages": [HumanMessage(content=message)],
        "question": message,
        "plan": {},
        "tools": [],
        "assets": [],
        "alarms": [],
        "candidate_alarms": [],
        "focus_alarm": None,
        "metadata": None,
        "summary": None,
        "trends": None,
        "correlation": None,
        "priorities": [],
        "recommendations": None,
        "documents": None,
        "refs": {},
        "warnings": [],
        "result": {},
    }


async def run_copilot(message: str, thread_id: str | None = None) -> dict:
    thread_id = thread_id or f"conv_{uuid.uuid4().hex[:12]}"
    trace_id = f"trace-{uuid.uuid4().hex[:12]}"

    connected = False
    try:
        async with open_toolbox(trace_id) as toolbox:
            connected = True
            config = {"configurable": {"thread_id": thread_id, "toolbox": toolbox}}
            state = await copilot_graph.ainvoke(fresh_turn_state(message), config=config)
    except Exception as error:
        if connected:
            raise  # a real bug inside the workflow - do not hide it
        # MCP server could not be started / reached -> degraded mode (documents only)
        config = {"configurable": {"thread_id": thread_id, "toolbox": None}}
        state = await copilot_graph.ainvoke(fresh_turn_state(message), config=config)
        state["result"]["warnings"].append(f"MCP connection error: {type(error).__name__}")

    result = state["result"]
    result["thread_id"] = thread_id
    return result
