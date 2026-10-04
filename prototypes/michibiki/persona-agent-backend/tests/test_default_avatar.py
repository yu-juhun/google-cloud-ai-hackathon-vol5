import default_avatar


def test_get_default_avatar_closed_reads_a_non_empty_png():
    data = default_avatar.get_default_avatar_closed()
    assert data.startswith(b"\x89PNG")
    assert len(data) > 0


def test_get_default_avatar_open_reads_a_non_empty_png():
    data = default_avatar.get_default_avatar_open()
    assert data.startswith(b"\x89PNG")
    assert len(data) > 0


def test_get_default_avatar_closed_caches_after_first_read(monkeypatch):
    default_avatar._closed_bytes = None
    calls = []
    real_open = open

    def counting_open(path, *args, **kwargs):
        calls.append(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", counting_open)

    default_avatar.get_default_avatar_closed()
    default_avatar.get_default_avatar_closed()

    assert len(calls) == 1
