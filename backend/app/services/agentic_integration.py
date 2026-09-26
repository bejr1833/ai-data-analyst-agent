"""
FastAPI integration entry point.

Import:
    from app.services.agentic_integration import analyze_dataset_question

Then call it from the dataset /ask endpoint.
"""

from app.services.agent import AnalystAgent


def analyze_dataset_question(
    dataset,
    question: str,
    conversation_history=None,
):
    agent = AnalystAgent(dataset)

    return agent.run(
        question,
        conversation_history=conversation_history,
    )
