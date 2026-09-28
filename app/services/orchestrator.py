"""
Backward-compatible facade for the AI Data Analyst Agent.

Existing imports of AnalystOrchestrator continue to work.
"""

from app.services.agent import AnalystAgent


class AnalystOrchestrator:
    def __init__(self, dataset):
        self.dataset = dataset
        self.agent = AnalystAgent(dataset)

    def analyze(self, question, conversation_history=None):
        return self.agent.run(
            question,
            conversation_history=conversation_history,
        )

    def plan(self, question):
        return self.agent.plan(question)

    def _detect_intent(self, question):
        steps = self.agent.plan(question)
        return steps[0].tool if steps else "general"
