import pytest
from fastapi.testclient import TestClient

from app import db, routes
from app.main import app

client = TestClient(app)  # no "with": the lifespan does not run, so no real pool is opened

BODY = {"placements": [{"id": "bottle-1", "type": "bottle", "coordinates": [10.2, -20.1]}], "durationDays": 1}


def simulate(session_id=None):
    body = BODY if session_id is None else {**BODY, "sessionId": session_id}
    response = client.post("/api/simulate", json=body)
    assert response.status_code == 200
    return response.json()["runId"]


@pytest.fixture
def fake_db(monkeypatch):
    """Pretend Tiger is connected and record what the app asks of it."""
    calls = {"saved_params": [], "deleted_sessions": [], "failures": 0}
    monkeypatch.setattr(db, "configured", lambda: True)
    monkeypatch.setattr(db, "available", lambda: True)
    monkeypatch.setattr(db, "save_run", lambda resp, req, start_time, parent_run_id:
                        calls["saved_params"].append(req.model_dump(by_alias=True, mode="json")))
    monkeypatch.setattr(db, "load_run", lambda run_id: None)

    def delete_session_runs(session_id):
        calls["deleted_sessions"].append(session_id)
        return 3

    def report_failure():
        calls["failures"] += 1

    monkeypatch.setattr(db, "delete_session_runs", delete_session_runs)
    monkeypatch.setattr(db, "report_failure", report_failure)
    return calls


def test_delete_removes_only_that_sessions_runs():
    mine = [simulate("session-a"), simulate("session-a")]
    theirs = simulate("session-b")
    anonymous = simulate()

    response = client.delete("/api/sessions/session-a/runs")

    assert response.status_code == 200
    assert response.json() == {"deleted": 2, "database": "unavailable"}
    for run_id in mine:
        assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/api/runs/{theirs}").status_code == 200
    assert client.get(f"/api/runs/{anonymous}").status_code == 200


def test_delete_for_a_session_with_no_runs_deletes_nothing():
    kept = simulate("session-b")
    assert client.delete("/api/sessions/session-a/runs").json() == {"deleted": 0, "database": "unavailable"}
    assert client.delete("/api/sessions/session-a/runs").json() == {"deleted": 0, "database": "unavailable"}
    assert client.get(f"/api/runs/{kept}").status_code == 200


def test_compare_runs_belong_to_the_session():
    data = client.post("/api/compare", json={**BODY, "sessionId": "session-a"}).json()
    assert client.delete("/api/sessions/session-a/runs").json()["deleted"] == 2
    assert client.get(f"/api/runs/{data['with']['runId']}").status_code == 404
    assert client.get(f"/api/runs/{data['without']['runId']}").status_code == 404


def test_session_id_is_stored_in_the_saved_request(fake_db):
    simulate("session-a")
    simulate()
    assert [params["sessionId"] for params in fake_db["saved_params"]] == ["session-a", None]


def test_delete_clears_the_database_and_reports_its_count(fake_db):
    run_id = simulate("session-a")
    response = client.delete("/api/sessions/session-a/runs")
    assert response.json() == {"deleted": 3, "database": "cleared"}
    assert fake_db["deleted_sessions"] == ["session-a"]
    assert client.get(f"/api/runs/{run_id}").status_code == 404  # the memory copy is gone too


def test_database_failure_during_delete_does_not_fail_the_request(fake_db, monkeypatch):
    def boom(session_id):
        raise RuntimeError("connection lost")

    monkeypatch.setattr(db, "delete_session_runs", boom)
    run_id = simulate("session-a")
    failures_before = fake_db["failures"]  # the snapshot lookup also reports failures: there is no real pool here
    response = client.delete("/api/sessions/session-a/runs")
    assert response.status_code == 200
    assert response.json() == {"deleted": 1, "database": "failed"}
    assert fake_db["failures"] == failures_before + 1
    assert run_id not in routes._runs


def test_database_in_cooldown_reports_failed_without_asking_it(fake_db, monkeypatch):
    simulate("session-a")
    monkeypatch.setattr(db, "available", lambda: False)
    response = client.delete("/api/sessions/session-a/runs")
    assert response.json() == {"deleted": 1, "database": "failed"}
    assert fake_db["deleted_sessions"] == []


@pytest.mark.parametrize("session_id", ["has space", "quote'", "x" * 65, ""])
def test_bad_session_id_in_the_body_is_422(session_id):
    response = client.post("/api/simulate", json={**BODY, "sessionId": session_id})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert routes._runs == {}


@pytest.mark.parametrize("session_id", ["has%20space", "quote%27", "x" * 65])
def test_bad_session_id_in_the_path_is_422(session_id):
    kept = simulate("session-a")
    response = client.delete(f"/api/sessions/{session_id}/runs")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert client.get(f"/api/runs/{kept}").status_code == 200


def test_evicted_runs_leave_the_session_index(monkeypatch):
    monkeypatch.setattr(routes, "MAX_STORED_RUNS", 2)
    for _ in range(3):
        simulate("session-a")
    assert len(routes._runs) == 2
    assert set(routes._run_sessions) == set(routes._runs)


def _fake_pool(monkeypatch, returned_rows):
    executed = []

    class Result:
        def fetchall(self):
            return returned_rows

    class Connection:
        def execute(self, sql, params):
            executed.append((" ".join(sql.split()), params))
            return Result()

    class Pool:
        opened = 0

        def connection(self):
            Pool.opened += 1

            class Scope:
                def __enter__(self):
                    return Connection()

                def __exit__(self, *exc):
                    return False

            return Scope()

    pool = Pool()
    monkeypatch.setattr(db, "_pool", pool)
    return pool, executed


def test_delete_session_runs_deletes_runs_first_then_their_positions_in_one_transaction(monkeypatch):
    pool, executed = _fake_pool(monkeypatch, [("run-1",), ("run-2",)])
    assert db.delete_session_runs("session-a") == 2
    assert pool.opened == 1
    assert len(executed) == 2
    runs_sql, runs_params = executed[0]
    assert runs_sql.startswith("DELETE FROM runs") and "RETURNING run_id" in runs_sql
    assert "params->>'sessionId' = %s" in runs_sql
    assert runs_params == ("session-a",)
    assert executed[1] == ("DELETE FROM positions WHERE run_id = ANY(%s)", (["run-1", "run-2"],))


def test_delete_session_runs_with_no_runs_skips_the_positions_delete(monkeypatch):
    pool, executed = _fake_pool(monkeypatch, [])
    assert db.delete_session_runs("session-a") == 0
    assert pool.opened == 1
    assert len(executed) == 1


def test_configured_is_false_without_a_pool(monkeypatch):
    monkeypatch.setattr(db, "_pool", None)
    assert db.configured() is False
    monkeypatch.setattr(db, "_pool", object())
    assert db.configured() is True
