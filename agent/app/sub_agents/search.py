def search_candidates(area: str, cuisine: str | None) -> list[dict]:
    """Stub: returns one fixed candidate regardless of input.
    Real implementation (Places API) replaces this body only —
    keep the return shape: list of {place_id, name, address, location, maps_url}.
    """
    return [
        {
            "place_id": "STUB_PLACE_1",
            "name": "スタブ食堂",
            "address": "福岡県福岡市中央区天神1-1-1",
            "location": {"latitude": 33.5904, "longitude": 130.4017},
            "maps_url": "https://www.google.com/maps/search/?api=1&query_place_id=STUB_PLACE_1",
        }
    ]
