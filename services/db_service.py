import os
import json
import sqlite3
import logging
from typing import List, Dict, Tuple, Any
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from services.env_loader import load_dotenv

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("db_service")

class DBService:
    def __init__(self, db_path: str = None, project_id: str = None):
        # Ensure .env variables are loaded into environment
        load_dotenv()
        
        self.db_path = db_path or os.environ.get("DATABASE_PATH") or "articles.db"
        self.project_id = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT") or "veo-testing"
        self.dataset_id = "news_articles_dataset"
        self.table_id = "article_embeddings_table"
        
        # Initialize Local SQLite
        self._init_sqlite()
        
        # Try to pre-check BigQuery client, fail gracefully if credentials aren't working
        self.bq_client = None
        try:
            from google.cloud import bigquery
            self.bq_client = bigquery.Client(project=self.project_id)
            logger.info("BigQuery client initialized successfully.")
        except Exception as e:
            logger.warning(f"Could not initialize BigQuery client: {e}. BigQuery sync will be disabled.")

    def _init_sqlite(self):
        """Initializes local SQLite schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                article_id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_number TEXT,
                headline TEXT,
                sub_headline TEXT,
                dateline_or_author TEXT,
                body_text TEXT,
                meta_description TEXT,
                primary_keyword TEXT,
                secondary_keywords TEXT, -- stored as JSON array
                tags TEXT,               -- stored as JSON array
                summary TEXT,
                embedding TEXT           -- stored as JSON array
            )
        """)
        conn.commit()
        conn.close()

    def save_article_local(self, article: Dict[str, Any]) -> int:
        """Saves a single article to local SQLite database."""
        is_gcp = os.environ.get("K_SERVICE") or os.environ.get("GAE_APPLICATION") or os.environ.get("DEPLOYMENT_ENV") == "GCP"
        
        # If on GCP, fetch max article_id from BQ to ensure no ID collision in autoincrement
        max_bq_id = 0
        if is_gcp and self.bq_client:
            try:
                query = f"SELECT MAX(article_id) as max_id FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`"
                query_job = self.bq_client.query(query)
                result = list(query_job.result())
                if result and result[0].max_id is not None:
                    max_bq_id = int(result[0].max_id)
            except Exception as e:
                logger.warning(f"Could not fetch max article_id from BQ: {e}")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if max_bq_id > 0:
            try:
                cursor.execute("SELECT MAX(article_id) FROM articles")
                row = cursor.fetchone()
                max_sqlite_id = row[0] if row and row[0] else 0
                if max_bq_id > max_sqlite_id:
                    cursor.execute("INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (?, ?)", ("articles", max_bq_id))
                    conn.commit()
            except Exception as e:
                logger.warning(f"Could not update sqlite_sequence: {e}")

        # Serialize lists to JSON strings
        sec_kw_str = json.dumps(article.get("secondary_keywords", []))
        tags_str = json.dumps(article.get("tags", []))
        embedding_str = json.dumps(article.get("embedding", []))
        
        cursor.execute("""
            INSERT INTO articles (
                page_number, headline, sub_headline, dateline_or_author, body_text,
                meta_description, primary_keyword, secondary_keywords, tags, summary, embedding
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            article.get("page_number"),
            article.get("headline"),
            article.get("sub_headline"),
            article.get("dateline_or_author"),
            article.get("body_text"),
            article.get("meta_description"),
            article.get("primary_keyword"),
            sec_kw_str,
            tags_str,
            article.get("summary"),
            embedding_str
        ))
        
        inserted_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return inserted_id

    def list_articles_local(self) -> List[Dict[str, Any]]:
        """Lists all stored articles from SQLite."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM articles ORDER BY article_id DESC")
        rows = cursor.fetchall()
        
        articles = []
        for row in rows:
            articles.append({
                "article_id": row["article_id"],
                "page_number": row["page_number"],
                "headline": row["headline"],
                "sub_headline": row["sub_headline"],
                "dateline_or_author": row["dateline_or_author"],
                "body_text": row["body_text"],
                "meta_description": row["meta_description"],
                "primary_keyword": row["primary_keyword"],
                "secondary_keywords": json.loads(row["secondary_keywords"] or "[]"),
                "tags": json.loads(row["tags"] or "[]"),
                "summary": row["summary"],
                "embedding": json.loads(row["embedding"] or "[]")
            })
            
        conn.close()
        return articles

    def list_articles_bigquery(self) -> List[Dict[str, Any]]:
        """Lists all stored articles from BigQuery."""
        if not self.bq_client:
            logger.warning("BigQuery client not initialized. Falling back to SQLite.")
            return self.list_articles_local()
            
        from google.cloud.exceptions import NotFound
        
        query = f"""
            SELECT article_id, page_number, headline, sub_headline, dateline_or_author,
                   body_text, meta_description, primary_keyword, secondary_keywords,
                   tags, summary, embedding
            FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
            ORDER BY article_id DESC
        """
        
        try:
            query_job = self.bq_client.query(query)
            rows = query_job.result()
            
            articles = []
            for row in rows:
                articles.append({
                    "article_id": row.article_id,
                    "page_number": row.page_number,
                    "headline": row.headline,
                    "sub_headline": row.sub_headline,
                    "dateline_or_author": row.dateline_or_author,
                    "body_text": row.body_text,
                    "meta_description": row.meta_description,
                    "primary_keyword": row.primary_keyword,
                    "secondary_keywords": list(row.secondary_keywords) if row.secondary_keywords else [],
                    "tags": list(row.tags) if row.tags else [],
                    "summary": row.summary,
                    "embedding": list(row.embedding) if row.embedding else []
                })
            return articles
        except NotFound:
            logger.warning("BigQuery table or dataset not found. Falling back to SQLite.")
            return self.list_articles_local()
        except Exception as e:
            logger.error(f"Error fetching articles from BigQuery: {e}. Falling back to SQLite.")
            return self.list_articles_local()

    def list_articles(self) -> List[Dict[str, Any]]:
        """Lists all stored articles, choosing BQ if on GCP, otherwise SQLite."""
        is_gcp = os.environ.get("K_SERVICE") or os.environ.get("GAE_APPLICATION") or os.environ.get("DEPLOYMENT_ENV") == "GCP"
        if is_gcp and self.bq_client:
            logger.info("GCP deployment detected. Fetching articles from BigQuery.")
            return self.list_articles_bigquery()
        else:
            logger.info("Local environment detected (or BQ not available). Fetching articles from SQLite.")
            return self.list_articles_local()

    def search_articles_local(self, query_embedding: List[float], top_n: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """
        Calculates cosine similarity between query embedding and stored local articles using NumPy.
        """
        articles = self.list_articles()
        
        results = []
        query_vector = np.array(query_embedding).reshape(1, -1)
        
        for article in articles:
            if article["embedding"] and len(article["embedding"]) > 0:
                article_vector = np.array(article["embedding"]).reshape(1, -1)
                # Calculate Cosine Similarity
                similarity = cosine_similarity(query_vector, article_vector)[0][0]
                results.append((article, float(similarity)))
        
        # Sort by similarity score in descending order
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_n]

    def search_articles(self, query_embedding: List[float], top_n: int = 5) -> List[Tuple[Dict[str, Any], float]]:
        """Alias for search_articles_local that searches across the active database."""
        return self.search_articles_local(query_embedding, top_n=top_n)

    def sync_to_bigquery(self, articles: List[Dict[str, Any]]):
        """
        Sends extracted articles to BigQuery if authenticated, failing gracefully if not.
        """
        if not self.bq_client:
            logger.warning("BigQuery client not initialized. Skipping BigQuery sync.")
            return
            
        from google.cloud import bigquery
        from google.cloud.exceptions import NotFound
        
        table_ref = self.bq_client.dataset(self.dataset_id).table(self.table_id)
        
        # Ensure Dataset exists
        try:
            self.bq_client.get_dataset(self.dataset_id)
        except NotFound:
            logger.info(f"Creating dataset '{self.dataset_id}'")
            dataset = bigquery.Dataset(self.bq_client.dataset(self.dataset_id))
            dataset.location = "US"
            self.bq_client.create_dataset(dataset, timeout=30)
            
        # Ensure Table exists
        schema = [
            bigquery.SchemaField("article_id", "INTEGER", mode="REQUIRED"),
            bigquery.SchemaField("page_number", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("headline", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("sub_headline", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("dateline_or_author", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("body_text", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("meta_description", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("primary_keyword", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("secondary_keywords", "STRING", mode="REPEATED"),
            bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
            bigquery.SchemaField("summary", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("embedding", "FLOAT", mode="REPEATED"),
        ]
        
        try:
            self.bq_client.get_table(table_ref)
        except NotFound:
            logger.info(f"Creating BigQuery table '{self.table_id}'")
            table = bigquery.Table(table_ref, schema=schema)
            self.bq_client.create_table(table)
            
        # Prepare rows to insert
        rows_to_insert = []
        for article in articles:
            rows_to_insert.append({
                "article_id": article.get("article_id"),
                "page_number": article.get("page_number"),
                "headline": article.get("headline"),
                "sub_headline": article.get("sub_headline"),
                "dateline_or_author": article.get("dateline_or_author"),
                "body_text": article.get("body_text"),
                "meta_description": article.get("meta_description"),
                "primary_keyword": article.get("primary_keyword"),
                "secondary_keywords": article.get("secondary_keywords", []),
                "tags": article.get("tags", []),
                "summary": article.get("summary"),
                "embedding": article.get("embedding", [])
            })
            
        if rows_to_insert:
            try:
                errors = self.bq_client.insert_rows_json(table_ref, rows_to_insert)
                if errors:
                    logger.error(f"BigQuery insertion errors: {errors}")
                else:
                    logger.info(f"Successfully inserted {len(rows_to_insert)} rows into BigQuery.")
            except Exception as e:
                logger.error(f"Failed to insert rows to BigQuery: {e}")
