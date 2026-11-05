import pytest
from sqlalchemy import select

from peopl import auth, copy, db, posts
from peopl.settings import load_settings

PEPPER = "test-secret"
DOMAINS = ("uchicago.edu",)
T0 = 1_800_000_000


@pytest.fixture()
def engine():
    return db.make_engine("sqlite:///:memory:")


def sign_up(engine, email, nick, now=T0, admin=False):
    sent = {}
    h = auth.request_code(engine, email, pepper=PEPPER, domains=DOMAINS, send=lambda e, c: sent.update(code=c), now=now)
    auth.verify_code(engine, email, sent["code"], pepper=PEPPER, now=now)
    admins = frozenset({h}) if admin else frozenset()
    return auth.create_user(engine, h, nick, admin_hashes=admins, now=now)


def plate(engine, user, **over):
    args = dict(
        body="Made dal, one plate left. Want it?",
        portions=1,
        place="Harper entrance",
        minutes=120,
        ingredients="Lentils, onion, ghee. Contains dairy.",
        tag="made_at_home",
        safe_ok=True,
        now=T0,
    )
    args.update(over)
    return posts.create_plate(engine, user, **args)


# ---------------------------------------------------------------- sign in


def test_only_university_emails_can_sign_in(engine):
    for bad in ("me@gmail.com", "me@uchicago.edu.evil.com", "nope", ""):
        with pytest.raises(auth.AuthError):
            auth.request_code(engine, bad, pepper=PEPPER, domains=DOMAINS, send=lambda e, c: None, now=T0)
    auth.request_code(engine, "Me@Harris.UChicago.edu ", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: None, now=T0)


def test_email_address_is_never_stored(engine):
    sign_up(engine, "private.person@uchicago.edu", "Sara")
    with engine.connect() as conn:
        for table in db.metadata.sorted_tables:
            for row in conn.execute(select(table)):
                assert "private.person" not in str(tuple(row))


def test_wrong_code_then_right_code(engine):
    sent = {}
    auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: sent.update(code=c), now=T0)
    wrong = "000000" if sent["code"] != "000000" else "111111"
    with pytest.raises(auth.AuthError, match="not right"):
        auth.verify_code(engine, "a@uchicago.edu", wrong, pepper=PEPPER, now=T0)
    assert auth.verify_code(engine, "a@uchicago.edu", sent["code"], pepper=PEPPER, now=T0)


def test_code_expires_and_works_once(engine):
    sent = {}
    auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: sent.update(code=c), now=T0)
    with pytest.raises(auth.AuthError, match="expired"):
        auth.verify_code(engine, "a@uchicago.edu", sent["code"], pepper=PEPPER, now=T0 + auth.CODE_TTL + 1)
    auth.verify_code(engine, "a@uchicago.edu", sent["code"], pepper=PEPPER, now=T0 + 5)
    with pytest.raises(auth.AuthError):
        auth.verify_code(engine, "a@uchicago.edu", sent["code"], pepper=PEPPER, now=T0 + 6)


def test_too_many_wrong_tries_locks_the_code(engine):
    sent = {}
    auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: sent.update(code=c), now=T0)
    wrong = "000000" if sent["code"] != "000000" else "111111"
    for _ in range(auth.MAX_ATTEMPTS):
        with pytest.raises(auth.AuthError):
            auth.verify_code(engine, "a@uchicago.edu", wrong, pepper=PEPPER, now=T0)
    with pytest.raises(auth.AuthError, match="Too many"):
        auth.verify_code(engine, "a@uchicago.edu", sent["code"], pepper=PEPPER, now=T0)


def test_new_code_replaces_old_and_requests_are_limited(engine):
    codes = []
    for i in range(auth.MAX_CODES_PER_HOUR):
        auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: codes.append(c), now=T0 + i)
    with pytest.raises(auth.AuthError, match="Too many codes"):
        auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: None, now=T0 + 10)
    if codes[0] != codes[-1]:
        with pytest.raises(auth.AuthError):
            auth.verify_code(engine, "a@uchicago.edu", codes[0], pepper=PEPPER, now=T0 + 10)


def test_send_failure_is_friendly(engine):
    def boom(e, c):
        raise OSError("smtp down")

    with pytest.raises(auth.AuthError, match="could not be sent"):
        auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=boom, now=T0)


def test_nicknames(engine):
    sign_up(engine, "a@uchicago.edu", "Sara")
    with pytest.raises(auth.AuthError, match="taken"):
        sign_up(engine, "b@uchicago.edu", "sara")
    for bad in ("x", "<script>", "a" * 30, "  "):
        with pytest.raises(auth.AuthError):
            auth.create_user(engine, "hash" + bad, bad)


def test_sessions_and_sign_out(engine):
    user = sign_up(engine, "a@uchicago.edu", "Sara")
    token = auth.create_session(engine, user["id"], pepper=PEPPER, now=T0)
    assert auth.get_user_for_token(engine, token, pepper=PEPPER, now=T0)["nickname"] == "Sara"
    assert auth.get_user_for_token(engine, token, pepper=PEPPER, now=T0 + auth.SESSION_TTL + 1) is None
    assert auth.get_user_for_token(engine, "wrong", pepper=PEPPER, now=T0) is None
    auth.sign_out(engine, token, pepper=PEPPER)
    assert auth.get_user_for_token(engine, token, pepper=PEPPER, now=T0) is None


def test_settings_parse():
    env = {"ALLOWED_DOMAINS": "uchicago.edu, @harris.edu", "ADMIN_EMAILS": "Boss@uchicago.edu", "DEV_SHOW_CODE": "1"}
    s = load_settings(lambda k: env.get(k, ""))
    assert s.domains == ("uchicago.edu", "harris.edu")
    assert len(s.admin_hashes) == 1 and s.dev_show_code and s.pepper_is_default


# ---------------------------------------------------------------- plates


def test_share_and_list_a_plate(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    plate(engine, cook, portions=2)
    items = posts.list_plates(engine, now=T0 + 60)
    assert len(items) == 1 and items[0]["state"] == "open" and items[0]["nickname"] == "Anaya"


def test_plate_rules(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    with pytest.raises(posts.PostError, match="safely"):
        plate(engine, cook, safe_ok=False)
    with pytest.raises(posts.PostError, match="ingredients"):
        plate(engine, cook, ingredients="")
    with pytest.raises(posts.PostError, match="pickup"):
        plate(engine, cook, place=" ")
    with pytest.raises(posts.PostError, match="too long"):
        plate(engine, cook, body="x" * 401)
    with pytest.raises(posts.PostError):
        plate(engine, cook, portions=0)
    with pytest.raises(posts.PostError):
        plate(engine, cook, tag="other")


def test_daily_post_limit(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    for _ in range(posts.DAILY_POST_LIMIT):
        plate(engine, cook)
    with pytest.raises(posts.PostError, match="tomorrow"):
        plate(engine, cook)


def test_claim_flow_and_all_shared(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    other = sign_up(engine, "c@uchicago.edu", "Cem")
    pid = plate(engine, cook, portions=1)
    posts.claim(engine, friend, pid, now=T0 + 10)
    with pytest.raises(posts.PostError, match="already|All shared"):
        posts.claim(engine, friend, pid, now=T0 + 11)
    with pytest.raises(posts.PostError, match="All shared"):
        posts.claim(engine, other, pid, now=T0 + 12)
    item = posts.list_plates(engine, now=T0 + 20)[0]
    assert item["state"] == "shared" and item["portions_left"] == 0


def test_cannot_claim_own_or_expired(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook, minutes=60)
    with pytest.raises(posts.PostError, match="own"):
        posts.claim(engine, cook, pid, now=T0 + 5)
    with pytest.raises(posts.PostError, match="passed"):
        posts.claim(engine, friend, pid, now=T0 + 3601)


def test_unclaim_gives_the_plate_back(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook, portions=1)
    posts.claim(engine, friend, pid, now=T0 + 5)
    posts.unclaim(engine, friend, pid)
    posts.unclaim(engine, friend, pid)  # a second tap must not add a plate
    assert posts.list_plates(engine, now=T0 + 6)[0]["portions_left"] == 1


def test_daily_claim_limit(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    ids = [plate(engine, cook, portions=2) for _ in range(posts.DAILY_CLAIM_LIMIT + 1)]
    for pid in ids[: posts.DAILY_CLAIM_LIMIT]:
        posts.claim(engine, friend, pid, now=T0 + 5)
    with pytest.raises(posts.PostError, match="tomorrow"):
        posts.claim(engine, friend, ids[-1], now=T0 + 6)


def test_ended_plates_sort_after_open_and_disappear(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    short = plate(engine, cook, minutes=60, body="Short one")
    longer = plate(engine, cook, minutes=600, body="Long one")
    items = posts.list_plates(engine, now=T0 + 7200)
    assert [p["id"] for p in items] == [longer, short]
    assert items[1]["state"] == "ended"
    assert [p["id"] for p in posts.list_plates(engine, now=T0 + 3600 + posts.GRACE + 5)] == [longer]


def test_rating_and_feedback_visible_to_cook(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook)
    with pytest.raises(posts.PostError):
        posts.rate_claim(engine, friend, pid, "delicious")
    posts.claim(engine, friend, pid, now=T0 + 5)
    with pytest.raises(posts.PostError):
        posts.rate_claim(engine, friend, pid, "terrible")
    posts.rate_claim(engine, friend, pid, "needs_salt", "  a bit more salt please ")
    row = posts.list_claimers(engine, pid)[0]
    assert row["nickname"] == "Bilal" and row["rating"] == "needs_salt" and row["note"] == "a bit more salt please"
    assert posts.my_claims(engine, friend["id"])[pid]["rating"] == "needs_salt"


def test_only_the_cook_can_close(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook)
    with pytest.raises(posts.PostError):
        posts.close_post(engine, friend, pid)
    posts.close_post(engine, cook, pid)
    assert posts.list_plates(engine, now=T0 + 5)[0]["state"] == "shared"


def test_replies(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook)
    posts.add_reply(engine, friend, pid, "Is it spicy?", now=T0 + 5)
    posts.add_reply(engine, cook, pid, "Medium!", now=T0 + 6)
    assert [r["body"] for r in posts.list_replies(engine, pid)] == ["Is it spicy?", "Medium!"]
    with pytest.raises(posts.PostError):
        posts.add_reply(engine, friend, pid, "   ", now=T0 + 7)


# ---------------------------------------------------------------- events


def test_only_organizers_post_events(engine):
    member = sign_up(engine, "a@uchicago.edu", "Anaya")
    admin = sign_up(engine, "boss@uchicago.edu", "Boss", admin=True)
    kwargs = dict(title="Friday iftar", body="Dinner after prayer.", starts_at=T0 + 86400, place="Ida Noyes", now=T0)
    with pytest.raises(posts.PostError, match="organizers"):
        posts.create_event(engine, member, **kwargs)
    posts.set_organizer(engine, admin, "anaya", True)
    member = auth.get_user(engine, member["id"])
    posts.create_event(engine, member, **kwargs)
    events = posts.list_events(engine, now=T0 + 10)
    assert [e["title"] for e in events] == ["Friday iftar"]
    with pytest.raises(posts.PostError, match="passed"):
        posts.create_event(engine, member, **{**kwargs, "starts_at": T0 - 7200})


def test_events_sorted_by_start(engine):
    admin = sign_up(engine, "boss@uchicago.edu", "Boss", admin=True)
    for title, offset in (("Later", 2 * 86400), ("Sooner", 86400)):
        posts.create_event(engine, admin, title=title, body="Come along.", starts_at=T0 + offset, place="Hall", now=T0)
    assert [e["title"] for e in posts.list_events(engine, now=T0)] == ["Sooner", "Later"]


# ---------------------------------------------------------------- moderation


def test_report_hide_ban(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    admin = sign_up(engine, "boss@uchicago.edu", "Boss", admin=True)
    pid = plate(engine, cook)
    posts.report_post(engine, friend, pid, "Looks unsafe", now=T0 + 5)
    with pytest.raises(posts.PostError, match="already"):
        posts.report_post(engine, friend, pid, "Looks unsafe", now=T0 + 6)
    with pytest.raises(posts.PostError):
        posts.list_reports(engine, friend)
    assert len(posts.list_reports(engine, admin)) == 1
    posts.hide_post(engine, admin, pid)
    assert posts.list_plates(engine, now=T0 + 10) == []
    assert posts.list_reports(engine, admin) == []


def test_ban_blocks_everything(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    admin = sign_up(engine, "boss@uchicago.edu", "Boss", admin=True)
    token = auth.create_session(engine, cook["id"], pepper=PEPPER, now=T0)
    plate(engine, cook)
    posts.ban_user(engine, admin, cook["id"])
    assert posts.list_plates(engine, now=T0 + 5) == []
    assert auth.get_user_for_token(engine, token, pepper=PEPPER, now=T0 + 5) is None
    with pytest.raises(auth.AuthError, match="can't sign in"):
        auth.request_code(engine, "a@uchicago.edu", pepper=PEPPER, domains=DOMAINS, send=lambda e, c: None, now=T0 + 5)
    with pytest.raises(posts.PostError, match="Admins can't"):
        posts.ban_user(engine, admin, admin["id"])


def test_delete_account_removes_everything(engine):
    cook = sign_up(engine, "a@uchicago.edu", "Anaya")
    friend = sign_up(engine, "b@uchicago.edu", "Bilal")
    pid = plate(engine, cook)
    posts.claim(engine, friend, pid, now=T0 + 5)
    posts.add_reply(engine, friend, pid, "Thanks!", now=T0 + 6)
    auth.delete_account(engine, cook["id"])
    assert auth.get_user(engine, cook["id"]) is None
    assert posts.list_plates(engine, now=T0 + 10) == []
    assert auth.get_user(engine, friend["id"]) is not None
    with engine.connect() as conn:
        assert conn.execute(select(db.claims)).all() == []
        assert conn.execute(select(db.replies)).all() == []


def test_copy_has_friendly_words():
    assert copy.CLAIM == "I'd love a plate"
    assert "donat" not in " ".join(
        [copy.PLATE_HINT, copy.PLATE_PLACEHOLDER, copy.CLAIM, copy.ALL_SHARED, *copy.TAGS.values()]
    ).lower()
