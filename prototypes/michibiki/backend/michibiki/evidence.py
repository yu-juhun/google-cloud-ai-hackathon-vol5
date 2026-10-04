"""Conservative checks on sourced measurements, independent of model verdicts."""
import re
import unicodedata


def compact(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value))


def measurement_supported(item, claims, place_name):
    quote = compact(item["quote"])
    terms = {"entrance_width": r"入口|出入口|扉|ドア|有効幅", "step_height": r"段差",
             "elevator_door_width": r"エレベーター|昇降機"}
    if not re.search(terms[item["kind"]], quote):
        return False
    numbers = re.findall(r"(\d+(?:\.\d+)?)(mm|cm|m|ミリメートル|センチメートル|メートル)", quote)
    factors = {"mm": .1, "cm": 1, "m": 100, "ミリメートル": .1, "センチメートル": 1, "メートル": 100}
    if not any(abs(float(number) * factors[unit] - item["value_cm"]) < .001 for number, unit in numbers):
        return False
    # A quote must occur in a cited, facility-specific grounding segment.
    return any(quote in compact(c["text"]) and compact(place_name) in compact(c["text"])
               and set(item["source_ids"]).issubset(c["source_ids"]) for c in claims)


def apply_condition_checks(assessment, profile, evidence, place_name):
    valid = {source["id"] for source in evidence.get("sources", [])}
    dimensions = [d for d in assessment.get("dimensions", [])
                  if set(d["source_ids"]).issubset(valid)
                  and measurement_supported(d, evidence.get("claims", []), place_name)]
    assessment["dimensions"] = dimensions
    checks = []
    for kind, label, limit in [("entrance_width", "入口の有効幅", profile["width"]),
                               ("step_height", "入口の段差", profile["step"])]:
        measurements = [d for d in dimensions if d["kind"] == kind]
        if not measurements:
            checks.append({"kind": kind, "label": label, "status": "unverified",
                           "detail": f"{'幅' if kind == 'entrance_width' else '段差'}の数値根拠は未取得。{'車いす対応の表示だけでは通行幅を判断できません。' if kind == 'entrance_width' else '段差なしとは断定していません。'}",
                           "source_ids": []})
            continue
        for d in measurements:
            fits = d["value_cm"] >= limit if kind == "entrance_width" else d["value_cm"] <= limit
            checks.append({"kind": kind, "label": label, "status": "within_condition" if fits else "outside_condition",
                           "detail": f"{d['point']}：公開値 {d['value_cm']:g}cm ／ あなたの条件 {limit:g}cm。" +
                                     ("数値上は条件内です。通行の余裕・経路全体は別に確認します。" if fits else "この箇所の数値は条件に合いません。別の入口・経路の確認が必要です。"),
                           "source_ids": d["source_ids"], "quote": d["quote"]})
    assessment["condition_checks"] = checks
    missing = any(c["status"] != "within_condition" for c in checks)
    if missing and assessment["status"] == "accessible":
        assessment["status"] = "uncertain"
    if assessment["status"] == "uncertain":
        # Missing dimensions cannot coexist with an unconditional prose verdict.
        assessment["fit_reason"] = re.sub(r"(利用|通行|移動)(は|が)?可能です|通れます|通行できます",
                                           "条件を満たすかはまだ判断できません", assessment["fit_reason"])
    speculative = [fact for fact in assessment["facts"] if re.search(r"可能性|推測|かもしれ|期待でき", fact)]
    assessment["facts"] = [fact for fact in assessment["facts"] if fact not in speculative]
    assessment["unknowns"] = list(dict.fromkeys([*assessment["unknowns"], *speculative]))


def guard_itinerary(itinerary, profile):
    limit = profile["stamina"]
    for stop in itinerary["stops"]:
        if stop["duration_minutes"] > limit:
            stop["rest_after"] = True
            stop["activity"] += f"（滞在中も、連続して動く場合は{limit}分以内に休憩を挟む案。休める設備は確認が必要です）"
    itinerary["assumptions"] = [text for text in itinerary["assumptions"]
                                if not ("営業時間" in text and re.search(r"仮定|想定", text))]
    itinerary["assumptions"].append("施設間の距離は直線距離です。車いすで通れる経路や移動時間を保証するものではありません。")
