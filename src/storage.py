import logging
import sqlite3

import pandas as pd
from .database import get_connection, initialize_database

logger = logging.getLogger(__name__)
MOVIE_COLUMNS = ["title", "release_year", "rating", "genre"]


class MovieStorage:
    def __init__(self, db_path="data/movies.db"):
        self.db_path = db_path
        initialize_database(self.db_path)

    def save(self, df):
        """Atomically replace the movie collection; keep SQL NULL values."""
        connection = get_connection(self.db_path)
        try:
            movies = df[MOVIE_COLUMNS].astype(object)
            movies = movies.where(pd.notna(movies), None)
            rows = movies.values.tolist()
            connection.execute("DELETE FROM movies")
            connection.executemany(
                "INSERT INTO movies (title, release_year, rating, genre) VALUES (?, ?, ?, ?)",
                rows,
            )
            connection.commit()
            logger.debug("Stored movies in SQLite: rows=%d", len(rows))
        except sqlite3.Error:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self):
        """Retrieve data to a DataFrame, without SQL IDs."""
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                "SELECT title, release_year, rating, genre FROM movies ORDER BY id"
            ).fetchall()
            return pd.DataFrame([dict(row) for row in rows], columns=MOVIE_COLUMNS)
        finally:
            connection.close()

    def select_columns(self, columns, limit=5):
        """Return SQL IDs and requested data columns in original row order."""
        self._validate_columns(columns)
        selected = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {selected} FROM movies ORDER BY id LIMIT ?", (limit,)
            ).fetchall()
            logger.debug("Selected movie columns=%s, returned_rows=%d", columns, len(rows))
            return [dict(row) for row in rows]
        finally:
            connection.close()

    def count_movies(self):
        connection = get_connection(self.db_path)
        try:
            return connection.execute("SELECT COUNT(*) FROM movies").fetchone()[0]
        finally:
            connection.close()

    def query_movies(self, columns, min_rating, limit):
        self._validate_columns(columns)
        selected = ", ".join(["id"] + columns)
        connection = get_connection(self.db_path)
        try:
            rows = connection.execute(
                f"SELECT {selected} FROM movies WHERE rating >= ? "
                "ORDER BY rating DESC, id ASC LIMIT ?",
                (min_rating, limit),
            ).fetchall()
            logger.debug("Queried movie columns=%s, returned_rows=%d", columns, len(rows))
            return [dict(row) for row in rows]
        finally:
            connection.close()

    @staticmethod
    def _validate_columns(columns):
        if not columns:
            logger.error("Select at least one column")
            raise ValueError("Select at least one column")
        for column in columns:
            if column not in MOVIE_COLUMNS:
                logger.error("Unsupported column: %s", column)
                raise ValueError(f"Unsupported column: {column}")
