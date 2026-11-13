# MP3 Movie API

This project uses FastAPI to upload and process movie CSV files. SQLite saves the movies so the data stays after restarting the API. The database.py and storage.py files handle saving, retrieving, and searching movies with SQL. The upload endpoint replaces the old movie collection with the new one. The processing endpoint uses the MP1 functions to clean the data. The cache.py file uses FakeRedis to store GET /movies results for 90 seconds. The cache is cleared after an upload or processing so the results stay up to date.

## Run

```bash
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload
```

## Tests

```bash
python -m pytest tests -v
```

## Example

POST /movies/process:

```json
{
  "validation": {
    "required_columns": ["title", "release_year", "rating", "genre"],
    "numeric_columns": ["release_year", "rating"]
  },
  "processing": {
    "remove_duplicates": true,
    "missing": {"enabled": true, "axis": "rows"},
    "outliers": {
      "enabled": true,
      "columns": ["rating"],
      "method": "iqr",
      "threshold": 1.5
    }
  }
}
```

Expected result with sample_movies.csv: 0 rows removed during validation, 20 rows before cleaning, 16 rows after cleaning, 4 rows removed, and 4 columns before and after.
