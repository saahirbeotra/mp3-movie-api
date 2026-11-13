import io
import json
import logging
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from data_pipeline.data_validator import validate_dataframe
from data_pipeline.data_processor import process_data, create_cleaning_report
from src import (
    HealthResponse, MovieCache, MovieDataResponse, MovieProcessingReport,
    MovieStorage, MovieUploadInfo, ProcessConfig, log_requests, setup_logging,
)
from src.storage import MOVIE_COLUMNS

setup_logging(verbose=True)
logger = logging.getLogger(__name__)
app = FastAPI(title="Movie Processing API", version="1.0.0")
app.middleware("http")(log_requests)
storage = MovieStorage()
cache = MovieCache()


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/upload", response_model=MovieUploadInfo)
async def upload_movies(file: UploadFile = File(...)):
    if Path(file.filename or "").suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    contents = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(contents))
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as error:
        raise HTTPException(status_code=400, detail="Unable to read CSV file") from error
    if len(df.columns) != len(MOVIE_COLUMNS) or set(df.columns) != set(MOVIE_COLUMNS):
        raise HTTPException(status_code=400, detail="CSV must contain exactly the movie columns")
    if df.empty:
        raise HTTPException(status_code=400, detail="CSV must contain at least one data row")
    df = df[MOVIE_COLUMNS]
    storage.save(df)
    cache.invalidate()
    logger.info("Uploaded movies: filename=%s, rows=%d", file.filename, len(df))
    return {"filename": file.filename, "rows": len(df), "columns": len(df.columns),
            "column_names": list(df.columns)}


@app.get("/movies", response_model=MovieDataResponse)
def get_movies(limit: int = Query(default=100, ge=1)):
    cached = cache.get(limit)
    if cached is not None:
        logger.info("Cache hit: retrieved movies with limit=%d", limit)
        return cached
    records = storage.select_columns(MOVIE_COLUMNS, limit)
    response = {"data": records, "total_rows": storage.count_movies()}
    cache.set(limit, response)
    logger.info("Retrieved movies: returned_rows=%d", len(records))
    return response


@app.get("/movies/search", response_model=list[dict])
def query_movies(
    columns: list[str] = Query(default=["title"]),
    min_rating: float = Query(default=0, ge=0, le=10),
    limit: int = Query(default=100, ge=1),
):
    try:
        results = storage.query_movies(columns, min_rating, limit)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    logger.info("Queried movies: columns=%s, min_rating=%s, returned_rows=%d",
                columns, min_rating, len(results))
    return results


@app.post("/movies/process", response_model=MovieProcessingReport)
def process_movies(config: ProcessConfig):
    df = storage.get()
    if df.empty:
        raise HTTPException(status_code=400, detail="No movies to process")
    settings = config.model_dump()
    try:
        validated = validate_dataframe(
            df.copy(),
            required_columns=settings["validation"]["required_columns"],
            numeric_columns=settings["validation"]["numeric_columns"],
        )
        validation_rows_removed = len(df) - len(validated)
        processed = process_data(validated.copy(), settings)
        report = create_cleaning_report(validated, processed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    storage.save(processed)
    cache.invalidate()
    logger.info("Processed movies: validation_removed=%d, rows_before=%d, rows_after=%d",
                validation_rows_removed, len(validated), len(processed))
    return {"validation_rows_removed": validation_rows_removed, "cleaning_report": report}
