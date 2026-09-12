# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.sub_agents.search import search_candidates
from app.sub_agents.judge import judge_accessibility
from app.sub_agents.recommend import build_recommendation_reason


MODEL = "gemini-3.7-flash"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


root_agent = Agent(
    name="agent",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="You are a helpful AI assistant designed to provide accurate and useful information.",
    tools=[get_weather, get_current_time],
)

app = App(
    root_agent=root_agent,
    name="app",
)


def run_pipeline(
    area: str,
    wheelchair_width_cm: float,
    cuisine: str | None = None,
    prompt: str | None = None,
) -> dict:
    """Barrier-free restaurant recommendation pipeline.

    Runs the search -> judge -> recommend stub sub-agents in sequence.
    Currently every sub-agent returns fixed dummy data; real
    implementations will replace each sub-agent's body only.
    """
    candidates = search_candidates(area=area, cuisine=cuisine)

    recommendations = []
    for place in candidates:
        accessibility = judge_accessibility(place, wheelchair_width_cm)
        reason = build_recommendation_reason(place, accessibility, prompt)
        recommendations.append(
            {
                "place_id": place["place_id"],
                "name": place["name"],
                "address": place["address"],
                "location": place["location"],
                "maps_url": place["maps_url"],
                "accessibility": accessibility,
                "recommendation_reason": reason,
            }
        )

    return {"recommendations": recommendations}
