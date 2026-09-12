from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types


MODEL = "gemini-3.7-flash"


def _agent(name: str, instruction: str) -> Agent:
    return Agent(
        name=name,
        model=Gemini(
            model=MODEL,
            retry_options=types.HttpRetryOptions(attempts=3),
        ),
        instruction=instruction,
    )


search_agent = _agent(
    "search",
    "Find restaurant candidates and collect their accessibility evidence.",
)
judge_agent = _agent(
    "judge",
    "Judge whether a restaurant is accessible for the supplied wheelchair width.",
)
recommend_agent = _agent(
    "recommend",
    "Rank judged restaurants and provide a concise recommendation reason.",
)

root_agent = _agent(
    "orchestrator",
    "Delegate restaurant recommendations in this order: search, judge, recommend.",
)
root_agent.sub_agents = [search_agent, judge_agent, recommend_agent]

app = App(root_agent=root_agent, name="app")
