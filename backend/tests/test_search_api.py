from app.models import Message, MessageRole
from app.models import Session as ChatSession

ALICE = {"email": "alice@example.com", "username": "alice", "password": "pw-alice-123"}
BOB = {"email": "bob@example.com", "username": "bob", "password": "pw-bob-123"}


def _signup(client, payload):
    resp = client.post("/auth/signup", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _logout(client):
    client.post("/auth/logout")
    client.cookies.clear()


def _seed_session(db_session, *, user_id, title, messages):
    chat = ChatSession(user_id=user_id, title=title)
    db_session.add(chat)
    db_session.flush()
    for role, content in messages:
        db_session.add(Message(session_id=chat.id, role=role, content=content))
    db_session.commit()
    db_session.refresh(chat)
    return chat


def _user_id(db_session, email):
    from app.models import User

    return db_session.query(User).filter_by(email=email).one().id


def test_search_requires_authentication(client):
    assert client.get("/search", params={"q": "hi"}).status_code == 401


def test_search_empty_q_returns_400(client):
    _signup(client, ALICE)
    assert client.get("/search").status_code == 400
    assert client.get("/search", params={"q": ""}).status_code == 400
    assert client.get("/search", params={"q": "   "}).status_code == 400


def test_search_matches_user_and_assistant_messages(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])

    s_user = _seed_session(
        db_session,
        user_id=uid,
        title="planning",
        messages=[(MessageRole.user, "how do I implement quicksort in python?")],
    )
    s_assistant = _seed_session(
        db_session,
        user_id=uid,
        title="algos",
        messages=[
            (MessageRole.user, "explain it"),
            (MessageRole.assistant, "quicksort is a divide-and-conquer algorithm."),
        ],
    )
    _seed_session(
        db_session,
        user_id=uid,
        title="unrelated",
        messages=[(MessageRole.user, "tell me a joke")],
    )

    resp = client.get("/search", params={"q": "quicksort"})
    assert resp.status_code == 200
    hits = resp.json()
    by_session = {h["session_id"]: h for h in hits}
    assert set(by_session) == {s_user.id, s_assistant.id}
    assert by_session[s_user.id]["matched_role"] == "user"
    assert by_session[s_assistant.id]["matched_role"] == "assistant"
    assert "quicksort" in by_session[s_user.id]["snippet"].lower()
    assert "quicksort" in by_session[s_assistant.id]["snippet"].lower()


def test_search_is_case_insensitive(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    _seed_session(
        db_session,
        user_id=uid,
        title="chat",
        messages=[(MessageRole.assistant, "Python is a great language")],
    )

    resp = client.get("/search", params={"q": "PYTHON"})
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_search_matches_session_title(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    chat = _seed_session(
        db_session,
        user_id=uid,
        title="trip to Iceland",
        messages=[(MessageRole.user, "something unrelated")],
    )

    resp = client.get("/search", params={"q": "iceland"})
    assert resp.status_code == 200
    hits = resp.json()
    assert len(hits) == 1
    assert hits[0]["session_id"] == chat.id
    assert hits[0]["matched_role"] is None
    assert "iceland" in hits[0]["snippet"].lower()


def test_search_prefers_message_match_over_title_match(client, db_session):
    """If both title and message match, the message wins so the caller gets
    a content snippet plus a concrete matched_role."""
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    chat = _seed_session(
        db_session,
        user_id=uid,
        title="banana bread recipe",
        messages=[(MessageRole.user, "what is banana bread?")],
    )

    resp = client.get("/search", params={"q": "banana"})
    hits = resp.json()
    assert len(hits) == 1
    hit = hits[0]
    assert hit["session_id"] == chat.id
    assert hit["matched_role"] == "user"
    assert "what is banana bread" in hit["snippet"].lower()


def test_search_is_user_scoped(client, db_session):
    """Alice's search must never surface Bob's sessions."""
    _signup(client, ALICE)
    alice_id = _user_id(db_session, ALICE["email"])
    _logout(client)

    _signup(client, BOB)
    bob_id = _user_id(db_session, BOB["email"])
    _seed_session(
        db_session,
        user_id=bob_id,
        title="bob secret",
        messages=[(MessageRole.user, "the special keyword appears here")],
    )
    _logout(client)

    # Alice has nothing with "special".
    client.post(
        "/auth/login",
        json={"email": ALICE["email"], "password": ALICE["password"]},
    )
    _seed_session(
        db_session,
        user_id=alice_id,
        title="alice chat",
        messages=[(MessageRole.user, "hello world")],
    )
    resp = client.get("/search", params={"q": "special"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_snippet_contains_context_around_match(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    prefix = "x" * 200
    suffix = "y" * 200
    content = f"{prefix}NEEDLE{suffix}"
    _seed_session(
        db_session,
        user_id=uid,
        title="long",
        messages=[(MessageRole.assistant, content)],
    )

    resp = client.get("/search", params={"q": "needle"})
    assert resp.status_code == 200
    snippet = resp.json()[0]["snippet"]

    # The match itself is present and flanked by exactly the context window
    # on each side (30 chars), with ellipsis markers because we clipped.
    assert "NEEDLE" in snippet
    assert snippet.startswith("…")
    assert snippet.endswith("…")
    # Inner content: 30 'x' + NEEDLE + 30 'y' = 66 chars, plus two ellipses.
    assert snippet == "…" + "x" * 30 + "NEEDLE" + "y" * 30 + "…"


def test_snippet_does_not_add_ellipsis_when_match_is_short(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    _seed_session(
        db_session,
        user_id=uid,
        title="short",
        messages=[(MessageRole.user, "hello there")],
    )

    resp = client.get("/search", params={"q": "hello"})
    snippet = resp.json()[0]["snippet"]
    assert snippet == "hello there"


def test_search_results_ordered_by_session_recency(client, db_session):
    from datetime import datetime, timedelta, timezone

    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])

    now = datetime.now(timezone.utc)
    old = _seed_session(
        db_session,
        user_id=uid,
        title="old",
        messages=[(MessageRole.user, "the needle is here")],
    )
    new = _seed_session(
        db_session,
        user_id=uid,
        title="new",
        messages=[(MessageRole.user, "the needle returns")],
    )
    # Nudge the timestamps so order is deterministic.
    db_session.get(ChatSession, old.id).updated_at = now - timedelta(hours=1)
    db_session.get(ChatSession, new.id).updated_at = now
    db_session.commit()

    resp = client.get("/search", params={"q": "needle"})
    ids = [h["session_id"] for h in resp.json()]
    assert ids == [new.id, old.id]


def test_search_caps_results_at_50_sessions(client, db_session):
    _signup(client, ALICE)
    uid = _user_id(db_session, ALICE["email"])
    for i in range(60):
        _seed_session(
            db_session,
            user_id=uid,
            title=f"session {i}",
            messages=[(MessageRole.user, f"msg {i} contains needle")],
        )

    resp = client.get("/search", params={"q": "needle"})
    assert resp.status_code == 200
    assert len(resp.json()) == 50
