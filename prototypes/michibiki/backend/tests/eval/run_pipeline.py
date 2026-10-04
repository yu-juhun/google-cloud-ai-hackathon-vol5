"""Generate grading traces from real Vertex + Places calls (no mocked results)."""

import asyncio
import json
import os
import subprocess
from pathlib import Path

from michibiki.agents import pipeline
from michibiki.contracts import Profile


async def main():
    os.environ["LOCAL_EXECUTION"] = "1"
    os.environ["PLACES_API_KEY"] = (
        await asyncio.to_thread(
            subprocess.check_output,
            [
                "gcloud",
                "secrets",
                "versions",
                "access",
                "latest",
                "--secret=michibiki-places-api-key",
                f"--project={os.environ['GOOGLE_CLOUD_PROJECT']}",
            ],
            text=True,
        )
    ).strip()
    output = Path("eval-results/traces")
    output.mkdir(parents=True, exist_ok=True)
    cases = [
        (
            "idol-unspecified",
            "東京・丸の内",
            "推し活をしたい、好きなアイドルの聖地巡礼をしたい",
            Profile(),
        ),
        (
            "quiet-breaks",
            "横浜・みなとみらい",
            "静かな美術館を楽しみたい。疲れる前にカフェで休憩したい。",
            Profile(step=0, stamina=10),
        ),
    ]
    for name, destination, wish, profile in cases:
        payload = {
            "trip": {
                "destination": destination,
                "date": "未定",
                "time": "10:00–16:00",
                "wish": wish,
            },
            "profile": profile.model_dump(),
            "idempotency_key": f"eval-{name}-001",
        }
        result = await pipeline(payload)
        trace = {
            "eval_cases": [
                {
                    "eval_case_id": name,
                    "prompt": {
                        "role": "user",
                        "parts": [{"text": json.dumps(payload, ensure_ascii=False)}],
                    },
                    "responses": [
                        {
                            "response": {
                                "role": "model",
                                "parts": [
                                    {"text": json.dumps(result, ensure_ascii=False)}
                                ],
                            }
                        }
                    ],
                    "context": json.dumps(result["places"], ensure_ascii=False),
                }
            ]
        }
        (output / f"{name}.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=2)
        )
        print(
            json.dumps(
                {
                    "case": name,
                    "status": result["status"],
                    "timings": result["timings"],
                    "model_calls": result["model_calls"],
                    "reports": len(result["twins"]),
                    "stops": len(result["itinerary"]["stops"]),
                    "clarification": result["clarification"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
