from fastapi.testclient import TestClient

import main


def test_root_static_files_are_served_directly():
    client = TestClient(main.app)

    response = client.get("/favicon.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    assert response.text.lstrip().startswith("<svg")


def test_spa_fallback_serves_index_for_client_routes():
    client = TestClient(main.app)

    response = client.get("/register-task")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<!doctype html>" in response.text.lower()


def test_api_routes_do_not_register_duplicate_method_paths():
    seen = set()
    duplicates = []
    for route in main.app.routes:
        methods = getattr(route, "methods", set()) or set()
        path = getattr(route, "path", "")
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            key = (method, path)
            if key in seen:
                duplicates.append(key)
            seen.add(key)

    assert duplicates == []
