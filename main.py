import os
import logging
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from services.env_loader import load_dotenv
# Load .env file parameters immediately on startup
load_dotenv()

from services.gemini_service import GeminiService
from services.db_service import DBService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="NewsLens AI - Newspaper Extraction Portal")

# CORS middleware for local development flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Services
# They will automatically detect environment variables (PROJECT_ID, etc.)
gemini_service = GeminiService()
db_service = DBService()

def process_single_article(raw_article: dict) -> dict:
    """Helper function to generate metadata and embeddings for a single article."""
    headline = raw_article.get("headline", "बिना शीर्षक का लेख")
    logger.info(f"Processing Article ID: {raw_article.get('article_id')} - Headline: {headline}")
    
    # Run Metadata Generation
    try:
        meta_data = gemini_service.generate_metadata(raw_article.get("body_text", ""))
    except Exception as e:
        logger.error(f"Failed metadata gen for article: {headline}. Error: {e}")
        meta_data = {
            "meta_description": f"News article headline: {headline}",
            "primary_keyword": "समाचार",
            "secondary_keywords": [],
            "tags": ["General"],
            "summmary": raw_article.get("body_text", "")[:200]
        }
    
    # Run Embedding Generation for the summary text
    summary_text = meta_data.get("summmary", meta_data.get("summary", "")) or raw_article.get("body_text", "")
    try:
        embedding = gemini_service.generate_embedding(summary_text)
    except Exception as e:
        logger.error(f"Failed embedding gen for article: {headline}. Error: {e}")
        embedding = []
        
    # Construct complete enriched article object
    return {
        "page_number": raw_article.get("page_number", "1"),
        "headline": raw_article.get("headline", "बिना शीर्षक का लेख"),
        "sub_headline": raw_article.get("sub_headline"),
        "dateline_or_author": raw_article.get("dateline_or_author"),
        "body_text": raw_article.get("body_text", ""),
        "meta_description": meta_data.get("meta_description"),
        "primary_keyword": meta_data.get("primary_keyword"),
        "secondary_keywords": meta_data.get("secondary_keywords", []),
        "tags": meta_data.get("tags", []),
        "summary": summary_text,
        "embedding": embedding
    }

# Request model for search
class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

@app.get("/api/articles")
def get_articles():
    """Retrieves the list of all processed newspaper articles."""
    try:
        articles = db_service.list_articles()
        return {"status": "success", "data": articles}
    except Exception as e:
        logger.error(f"Error fetching articles: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/search")
def search_articles(payload: SearchRequest):
    """Vector similarity search across extracted articles using Gemini Embeddings."""
    try:
        if not payload.query.strip():
            raise HTTPException(status_code=400, detail="Search query cannot be empty")
            
        # 1. Generate embedding for query text
        logger.info(f"Generating embedding for query: {payload.query}")
        query_embedding = gemini_service.generate_embedding(payload.query)
        
        # 2. Run Cosine Similarity Search
        results = db_service.search_articles(query_embedding, top_n=payload.limit)
        
        # 3. Format output
        formatted_results = []
        for article, score in results:
            # Attach the similarity score to response
            article_copy = article.copy()
            article_copy["similarity_score"] = score
            formatted_results.append(article_copy)
            
        return {"status": "success", "data": formatted_results}
    except Exception as e:
        logger.error(f"Error performing search: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Uploads a newspaper PDF and processes it through the full pipeline:
    1. Extraction -> 2. Metadata Gen -> 3. Embedding calculation -> 4. Storage.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        
    try:
        logger.info(f"Reading uploaded file: {file.filename}")
        pdf_bytes = await file.read()
        
        # Step 1: Extract Hindi articles from PDF using Gemini 3.1 Pro
        logger.info("Step 1: Extracting articles using Gemini Pro...")
        extracted_articles = gemini_service.extract_articles(pdf_bytes)
        logger.info(f"Extracted {len(extracted_articles)} articles.")
        
        # Step 2 & 3: Generate Metadata & Embeddings for each article in parallel
        logger.info(f"Step 2 & 3: Generating metadata & embeddings in parallel for {len(extracted_articles)} articles...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            enriched_articles = list(executor.map(process_single_article, extracted_articles))
            
        processed_articles = []
        
        # Step 3.5: Save to local SQLite database sequentially
        for enriched_article in enriched_articles:
            local_id = db_service.save_article_local(enriched_article)
            enriched_article["article_id"] = local_id
            processed_articles.append(enriched_article)
            
        # Step 4: Sync all successfully processed articles to BigQuery in background
        try:
            db_service.sync_to_bigquery(processed_articles)
        except Exception as e:
            logger.error(f"Failed syncing to BigQuery: {e}")
            
        return {
            "status": "success",
            "message": f"Processed {len(processed_articles)} articles successfully.",
            "data": processed_articles
        }
        
    except Exception as e:
        logger.error(f"Pipeline processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Error during pipeline processing: {str(e)}")

# Request model for GCS Path Upload
class GcsProcessRequest(BaseModel):
    gcs_uri: str

@app.post("/api/process-gcs")
def process_gcs_pdf(payload: GcsProcessRequest):
    """
    Processes a newspaper PDF located in a GCS bucket:
    1. Extraction from GCS -> 2. Metadata Gen -> 3. Embedding calculation -> 4. Storage.
    """
    if not payload.gcs_uri.strip().startswith("gs://") or not payload.gcs_uri.strip().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid GCS URI. Must be a gs:// link pointing to a PDF file.")
        
    try:
        gcs_path = payload.gcs_uri.strip()
        logger.info(f"Processing GCS PDF URI: {gcs_path}")
        
        # Step 1: Extract articles from GCS using Gemini
        logger.info("Step 1: Extracting articles from GCS...")
        extracted_articles = gemini_service.extract_articles_from_gcs(gcs_path)
        logger.info(f"Extracted {len(extracted_articles)} articles from GCS.")
        
        # Step 2 & 3: Generate Metadata & Embeddings for each article in parallel
        logger.info(f"Step 2 & 3: Generating metadata & embeddings in parallel for {len(extracted_articles)} articles...")
        with ThreadPoolExecutor(max_workers=10) as executor:
            enriched_articles = list(executor.map(process_single_article, extracted_articles))
            
        processed_articles = []
        
        # Step 3.5: Save to local SQLite database sequentially
        for enriched_article in enriched_articles:
            local_id = db_service.save_article_local(enriched_article)
            enriched_article["article_id"] = local_id
            processed_articles.append(enriched_article)
            
        # Step 4: Sync to BigQuery
        try:
            db_service.sync_to_bigquery(processed_articles)
        except Exception as e:
            logger.error(f"Failed syncing to BigQuery: {e}")
            
        return {
            "status": "success",
            "message": f"Processed {len(processed_articles)} articles from GCS successfully.",
            "data": processed_articles
        }
        
    except Exception as e:
        logger.error(f"GCS pipeline processing error: {e}")
        raise HTTPException(status_code=500, detail=f"Error during GCS pipeline processing: {str(e)}")

# Request model for Newspaper Layout Generation
class LayoutGenerationRequest(BaseModel):
    article_ids: List[int]
    persona: str

@app.post("/api/generate-layout")
def generate_newspaper_layout_api(payload: LayoutGenerationRequest):
    """
    Generates a customized responsive HTML newspaper layout using Gemini 3.1 Pro
    based on the selected article IDs and reader persona style.
    """
    if not payload.article_ids:
        raise HTTPException(status_code=400, detail="Please select at least one article.")
        
    try:
        logger.info(f"Generating layout for articles: {payload.article_ids} using persona: {payload.persona}")
        
        # 1. Fetch all stored articles
        all_articles = db_service.list_articles()
        
        # 2. Filter out selected articles by ID
        selected_articles = []
        for article_id in payload.article_ids:
            match = next((art for art in all_articles if art["article_id"] == article_id), None)
            if match:
                selected_articles.append(match)
                
        if not selected_articles:
            raise HTTPException(status_code=404, detail="None of the selected articles were found in the database.")
            
        # 3. Call Gemini layout editor service
        generated_html = gemini_service.generate_newspaper_layout(selected_articles, payload.persona)
        
        return {
            "status": "success",
            "html": generated_html
        }
        
    except Exception as e:
        logger.error(f"Layout generation API error: {e}")
        raise HTTPException(status_code=500, detail=f"Error during layout generation: {str(e)}")

# Serve Frontend Static Files
# Mount the static frontend folder at root (/)
# Check if frontend directory exists, if not create it later
os.makedirs("frontend", exist_ok=True)
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")
