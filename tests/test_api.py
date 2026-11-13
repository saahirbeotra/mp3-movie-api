import pytest
import main
from src import MovieStorage


def test_movies_persist(client, test_storage, uploaded_movies):
    reopened = MovieStorage(test_storage.db_path)
    movies = reopened.get()
    assert len(movies) == 20
    assert list(movies.columns) == ["title", "release_year", "rating", "genre"]
    assert movies["title"].tolist()[:4] == ["Movie A", "Movie B", "Movie B", "Movie C"]
    assert reopened.count_movies() == 20
    db_rows = reopened.select_columns(["title"], limit=100)
    response = client.get("/movies", params={"limit": 100})
    assert response.status_code == 200
    assert [x["id"] for x in db_rows] == list(range(1, 21))
    assert [x["id"] for x in response.json()["data"]] == list(range(1, 21))


def test_cache_and_processing(client, uploaded_movies, processing_body):
    for limit in (100, 1):
        response = client.get("/movies", params={"limit": limit})
        assert response.status_code == 200
        assert main.cache.get(limit) == response.json()
    repeated = client.get("/movies", params={"limit": 100})
    assert repeated.status_code == 200
    assert repeated.json()["total_rows"] == 20
    result = client.post("/movies/process", json=processing_body)
    assert result.status_code == 200, result.text
    report = result.json()
    assert report["validation_rows_removed"] == 0
    assert report["cleaning_report"] == {
        "rows_before": 20, "rows_after": 16, "rows_removed": 4,
        "columns_before": 4, "columns_after": 4, "columns_removed": 0,
    }
    assert main.cache.get(100) is None
    assert main.cache.get(1) is None
    final = client.get("/movies", params={"limit": 100})
    assert final.status_code == 200
    assert final.json()["total_rows"] == 16
    records = final.json()["data"]
    assert len(records) == 16
    assert [x["id"] for x in records] == list(range(1, 17))
    assert [x["title"] for x in records] == [f"Movie {x}" for x in "ABCDEFGHIJKLMNOP"]
    assert main.cache.get(100) == final.json()


def test_cache_hit_skips_database(client, uploaded_movies, monkeypatch):
    first = client.get("/movies", params={"limit": 100})
    assert first.status_code == 200

    def fail_if_called(*args, **kwargs):
        pytest.fail("Database should not be accessed on a cache hit")

    monkeypatch.setattr(main.storage, "select_columns", fail_if_called)
    monkeypatch.setattr(main.storage, "count_movies", fail_if_called)
    second = client.get("/movies", params={"limit": 100})
    assert second.status_code == 200
    assert second.json() == first.json()


def test_invalid_upload_keeps_data(client, uploaded_movies):
    response = client.post("/upload", files={"file": ("invalid.csv", b"bad,col\na,b", "text/csv")})
    assert response.status_code == 400
    assert client.get("/movies").json()["total_rows"] == 20


def test_search_and_replacement(client, uploaded_movies, sample_csv_bytes):
    response = client.get("/movies/search", params={"columns": ["title", "rating"], "min_rating": 8.5, "limit": 2})
    assert response.status_code == 200
    assert response.json() == [
        {"id": 4, "title": "Movie C", "rating": 9.0},
        {"id": 2, "title": "Movie B", "rating": 8.5},
    ]
    assert client.get("/movies/search", params={"columns": "bad"}).status_code == 400
    again = client.post("/upload", files={"file": ("sample_movies.csv", sample_csv_bytes, "text/csv")})
    assert again.status_code == 200
    assert client.get("/movies").json()["total_rows"] == 20
