from langgraph.graph import END, START, StateGraph

from app.graph.nodes.architect import architect_node
from app.graph.nodes.feasibility_analyst import feasibility_analyst_node
from app.graph.nodes.human_gate import human_gate_node
from app.graph.nodes.planner import planner_node
from app.graph.nodes.prompt_builder import prompt_builder_node
from app.graph.nodes.requirement_analyst import requirement_analyst_node
from app.graph.nodes.reviewer import reviewer_node
from app.graph.nodes.supervisor import supervisor_node
from app.graph.routes import next_route
from app.graph.state import ProjectState
from app.storage.checkpoints import get_checkpointer


def build_graph():
    graph = StateGraph(ProjectState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("requirement_analyst", requirement_analyst_node)
    graph.add_node("feasibility_analyst", feasibility_analyst_node)
    graph.add_node("architect", architect_node)
    graph.add_node("planner", planner_node)
    graph.add_node("prompt_builder", prompt_builder_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("human_gate", human_gate_node)

    graph.add_edge(START, "supervisor")

    graph.add_conditional_edges(
        "supervisor",
        next_route,
        {
            "requirement_analyst": "requirement_analyst",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "requirement_analyst",
        next_route,
        {
            "feasibility_analyst": "feasibility_analyst",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "feasibility_analyst",
        next_route,
        {
            "architect": "architect",
            "human_gate": "human_gate",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "architect",
        next_route,
        {
            "planner": "planner",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "planner",
        next_route,
        {
            "prompt_builder": "prompt_builder",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "prompt_builder",
        next_route,
        {
            "reviewer": "reviewer",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "reviewer",
        next_route,
        {
            "planner": "planner",
            "prompt_builder": "prompt_builder",
            "finish": END,
        },
    )
    graph.add_conditional_edges(
        "human_gate",
        next_route,
        {
            "requirement_analyst": "requirement_analyst",
            "finish": END,
        },
    )

    return graph.compile(checkpointer=get_checkpointer())
