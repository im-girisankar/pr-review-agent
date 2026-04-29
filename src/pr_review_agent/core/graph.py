from langgraph.graph import END, START, StateGraph

from .state import ReviewState


def build_graph() -> StateGraph:
    """Build and return the review graph. Nodes are wired in later phases."""
    graph = StateGraph(ReviewState)
    # Nodes and edges will be added as phases are implemented
    return graph
