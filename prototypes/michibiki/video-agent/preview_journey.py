"""Operator CLI: saved itinerary + personal/venue references -> Veo -> smooth MP4.

Runs with the backend virtualenv (ADC, Cloud SQL connector, requests, SQLAlchemy).
Artifacts contain no credentials. A manifest resumes existing Veo operations;
re-running never submits a new operation for a scene that already has one.
"""
import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google import genai
from google.genai import types
import requests
from sqlalchemy import select

from journey import compose, scene_prompt
from veo_client import VEO_MODEL

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from michibiki import db


def write_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def image_mime(raw):
    if raw.startswith(b'\xff\xd8'):
        return 'image/jpeg'
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    raise ValueError('Veo references must be JPEG or PNG')


def reference(title, work, ordinal):
    session = requests.Session()
    session.headers["User-Agent"] = "MichibikiJourneyPrototype/1.0"
    response = session.get("https://commons.wikimedia.org/w/api.php", params={
        "action": "query", "format": "json", "titles": title, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 1280}, timeout=30)
    response.raise_for_status()
    page = next(iter(response.json()["query"]["pages"].values()))
    info = page["imageinfo"][0]
    metadata = info["extmetadata"]
    license_name = metadata.get("LicenseShortName", {}).get("value", "")
    if license_name not in ("CC0", "Public domain", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0"):
        raise ValueError(f"Unapproved reference license: {license_name}")
    path = work / f"reference-{ordinal}.jpg"
    if not path.exists():
        # The original URL is a fallback for Wikimedia thumbnail throttling.
        for url in dict.fromkeys([info.get("thumburl", info["url"]), info["url"]]):
            response = session.get(url, timeout=45)
            if response.ok and response.headers.get("Content-Type", "").startswith("image/"):
                path.write_bytes(response.content)
                break
        else:
            raise RuntimeError("Venue reference download failed; do not silently substitute another place")
    return path, {"title": title, "source": info["descriptionurl"], "license": license_name,
                  "license_url": metadata.get("LicenseUrl", {}).get("value", ""),
                  "author": html.unescape(re.sub("<[^>]+>", "", metadata.get("Artist", {}).get("value", "")))}


def load_mission(project, mission_id):
    if not os.environ.get("DATABASE_URL"):
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        response = AuthorizedSession(credentials).get(
            f"https://secretmanager.googleapis.com/v1/projects/{project}/secrets/michibiki-db-password/versions/latest:access", timeout=20)
        response.raise_for_status()
        os.environ.update(INSTANCE_CONNECTION_NAME=f"{project}:asia-northeast1:michibiki-db",
                          DB_USER="michibiki", DB_NAME="michibiki",
                          DB_PASSWORD=base64.b64decode(response.json()["payload"]["data"]).decode())
    with db.engine().connect() as connection:
        mission = connection.execute(select(db.missions).where(db.missions.c.id == mission_id)).mappings().one()
    if mission["status"] != "completed":
        raise ValueError("Use an existing completed itinerary, not a failed analysis")
    return mission


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--person", type=Path, required=True)
    parser.add_argument("--locations", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--output-name", default="journey.mp4")
    parser.add_argument("--head-trims", default="", help="Reviewed seconds to trim at each scene start, e.g. 0,2,2,2")
    parser.add_argument("--prepare-only", action="store_true", help="Fetch references and write prompts, no paid Veo call")
    args = parser.parse_args()
    if Path(args.output_name).name != args.output_name or not args.output_name.endswith('.mp4'):
        raise ValueError("Use a simple MP4 output filename")
    work = args.output_dir.resolve()
    work.mkdir(parents=True, exist_ok=True)
    person = args.person.read_bytes()
    person_mime = image_mime(person)
    fingerprint = hashlib.sha256(person).hexdigest()
    manifest_path = work / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"person_sha256": fingerprint, "mission_id": args.mission_id, "scenes": []}
    if manifest["person_sha256"] != fingerprint or manifest["mission_id"] != args.mission_id:
        raise ValueError("Use a new output directory for a different person or mission")
    mission = load_mission(args.project, args.mission_id)
    locations = json.loads(args.locations.read_text(encoding="utf-8"))
    stops = mission["result"]["itinerary"]["stops"]
    if len(locations) != len(stops) or not 2 <= len(stops) <= 4:
        raise ValueError("This bounded preview supports two to four itinerary stops")
    prepared, credits = [], []
    for i, (stop, location) in enumerate(zip(stops, locations)):
        if stop["place_id"] != location["place_id"]:
            raise ValueError("Reference location does not match the actual itinerary stop")
        path, credit = reference(location["commons_file"], work, i + 1)
        prompt = scene_prompt(mission["input_snapshot"]["trip"], stop, location, i, len(stops), mission["input_snapshot"]["profile"]["chair"])
        (work / f"scene-{i + 1}-prompt.txt").write_text(prompt, encoding="utf-8")
        prepared.append((location, path, prompt))
        credits.append(credit)
        if len(manifest["scenes"]) <= i:
            manifest["scenes"].append({"place": location["name"], "reference": credit})
        prompt_sha = hashlib.sha256(prompt.encode()).hexdigest()
        entry = manifest["scenes"][i]
        if entry.get("operation") and entry.get("prompt_sha256") != prompt_sha:
            raise ValueError("Changed prompt: choose a new output directory, do not reuse old clips")
        entry["prompt_sha256"] = prompt_sha
    write_json(manifest_path, manifest)
    write_json(work / "reference-credits.json", credits)
    print({"references_ready": len(prepared), "new_clips_remaining": sum(not (work / f'scene-{i + 1}.mp4').exists() for i in range(len(prepared))),
           "paid_generation_enabled": not args.prepare_only}, flush=True)
    if args.prepare_only:
        return
    client = genai.Client(vertexai=True, project=args.project, location="us-central1",
                          http_options=types.HttpOptions(timeout=120000, retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        for i, (location, reference_path, prompt) in enumerate(prepared):
            clip = work / f"scene-{i + 1}.mp4"
            if clip.exists():
                continue
            entry = manifest["scenes"][i]
            if not entry.get("operation"):
                venue_bytes = reference_path.read_bytes()
                references = [types.VideoGenerationReferenceImage(image=types.Image(image_bytes=person, mime_type=person_mime), reference_type="asset"),
                              types.VideoGenerationReferenceImage(image=types.Image(image_bytes=venue_bytes, mime_type=image_mime(venue_bytes)), reference_type="asset")]
                previous = work / f"scene-{i}-last-frame.png"
                if i and previous.exists():
                    references.append(types.VideoGenerationReferenceImage(image=types.Image(image_bytes=previous.read_bytes(), mime_type="image/png"), reference_type="asset"))
                print({"starting_scene": i + 1, "place": location["name"], "references": len(references)}, flush=True)
                operation = client.models.generate_videos(model=VEO_MODEL,
                    source=types.GenerateVideosSource(prompt=prompt),
                    config=types.GenerateVideosConfig(reference_images=references, number_of_videos=1,
                        duration_seconds=8, aspect_ratio="16:9", resolution="720p", person_generation="allow_adult", generate_audio=True))
                entry["operation"] = operation.name
                write_json(manifest_path, manifest)
            for attempt in range(60):
                try:
                    operation = client.operations.get(types.GenerateVideosOperation(name=entry["operation"]))
                except genai.errors.APIError as exc:
                    if exc.code not in (429, 500, 502, 503, 504):
                        raise
                    print({"scene": i + 1, "poll_retry_status": exc.code}, flush=True)
                    time.sleep(10)
                    continue
                if operation.done:
                    if operation.error or not operation.result or not operation.result.generated_videos:
                        entry["status"] = "failed"
                        write_json(manifest_path, manifest)
                        raise RuntimeError(f"Scene {i + 1} failed or was filtered; do not automatically resubmit")
                    raw = operation.result.generated_videos[0].video.video_bytes
                    if not raw:
                        raise RuntimeError("Veo returned no inline video bytes")
                    clip.write_bytes(raw)
                    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-sseof", "-0.1", "-i", str(clip),
                                    "-frames:v", "1", str(work / f"scene-{i + 1}-last-frame.png")], check=True)
                    entry["status"] = "ready"
                    write_json(manifest_path, manifest)
                    print({"scene_ready": i + 1, "bytes": len(raw)}, flush=True)
                    break
                time.sleep(10)
            else:
                raise TimeoutError("Still generating; resume the same manifest, do not start another operation")
        final = work / args.output_name
        if not final.exists():
            font = next((str(p) for p in [Path('/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc'), Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')] if p.exists()), None)
            manifest["render"] = compose([work / f"scene-{i + 1}.mp4" for i in range(len(prepared))], final,
                                         [location["name"] for location, _, _ in prepared], font=font,
                                         credit_text="実景参考: Wikimedia Commons\n" + "\n".join(
                                             f"{a} / {l}" for a,l in sorted({(c['author'],c['license']) for c in credits})),
                                         head_trims=[float(t) for t in args.head_trims.split(',')] if args.head_trims else None)
            write_json(manifest_path, manifest)
        print({"output": str(final), "render": manifest.get("render")}, flush=True)
    finally:
        client.close()


if __name__ == "__main__":
    main()
