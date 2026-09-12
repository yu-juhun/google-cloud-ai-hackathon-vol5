from app.agent import run_pipeline


def test_stub_pipeline_returns_fixed_shape():
    result = run_pipeline(
        area="福岡市中央区",
        wheelchair_width_cm=63,
        cuisine="イタリアン",
        prompt="入口に段差がなく、トイレも使いやすい店がよい",
    )

    assert "recommendations" in result
    assert len(result["recommendations"]) == 1

    rec = result["recommendations"][0]
    assert rec["place_id"] == "STUB_PLACE_1"
    assert rec["name"] == "スタブ食堂"
    assert rec["accessibility"]["status"] == "accessible"
    assert rec["accessibility"]["confidence"] == "low"
    assert rec["accessibility"]["reasons"][0]["condition"] == "entrance"
    assert "recommendation_reason" in rec
