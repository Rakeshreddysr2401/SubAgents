"""Graph assembly.

Parent graph:  START → recall_memories → assistant(swarm) → END

The swarm is compiled as a subgraph node. Handoff tools inside the agents use
Command(graph=Command.PARENT), which resolves to the swarm (one level up from
each react agent) regardless of the extra parent wrapper.
"""

from langgraph.graph import END, START, StateGraph

from src.graph.state import VisualAssistantState
from src.graph.swarm import build_swarm_graph
from src.memory.recall import make_recall_node


def build_graph(checkpointer=None, mem0=None):
    """Compile the full assistant graph.

    Must be called after apply_swiggy_tools() (see src/app.py lifespan).
    Pass a Mem0 instance to enable per-turn memory recall; None disables it.
    """
    swarm = build_swarm_graph().compile()

    parent = StateGraph(VisualAssistantState)
    parent.add_node("recall_memories", make_recall_node(mem0))
    parent.add_node("assistant", swarm)
    parent.add_edge(START, "recall_memories")
    parent.add_edge("recall_memories", "assistant")
    parent.add_edge("assistant", END)
    return parent.compile(checkpointer=checkpointer)
