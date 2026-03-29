"""
FastAPI Application
Main API for the RAG chatbot
"""

import logging
import os
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from config import (
    API_HOST,
    API_PORT,
    RELOAD_API,
    UPLOAD_DIRECTORY,
    MAX_FILE_SIZE_MB,
    LOG_LEVEL,
    LOG_FILE,
)
from document_processor import DocumentProcessor
from rag_pipeline import get_rag_pipeline
from vector_store import get_vector_store

# Setup logging
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    description="Retrieval-Augmented Generation Chatbot API",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
document_processor = DocumentProcessor()
rag_pipeline = get_rag_pipeline()


# ============= Request/Response Models =============

class QueryRequest(BaseModel):
    """Query request model"""
    query: str
    k: int = 5
    rewrite_query: bool = True


class QueryResponse(BaseModel):
    """Query response model"""
    answer: str
    query: str
    retrieved_documents: List[dict]
    timestamp: str
    document_count: int


class UploadResponse(BaseModel):
    """Upload response model"""
    filename: str
    chunks_created: int
    documents_added: int
    timestamp: str


class StatsResponse(BaseModel):
    """Statistics response model"""
    llm_model: str
    vector_db_type: str
    embedding_model: str
    embedding_dimension: int
    total_documents: int
    memory_enabled: bool
    query_rewriting_enabled: bool


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    version: str


# ============= API Endpoints =============

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }


@app.get("/stats", response_model=StatsResponse)
async def get_stats():
    """Get RAG pipeline statistics"""
    logger.info("Stats requested")
    try:
        stats = rag_pipeline.get_stats()
        return stats
    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """Upload and process a document"""
    logger.info(f"Document upload requested: {file.filename}")
    
    try:
        # Validate file
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file selected")
        
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in document_processor.supported_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported file type: {file_ext}"
            )
        
        # Check file size
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size_mb:.2f}MB (max: {MAX_FILE_SIZE_MB}MB)"
            )
        
        # Save file
        file_path = os.path.join(UPLOAD_DIRECTORY, file.filename)
        with open(file_path, "wb") as f:
            f.write(content)
        
        logger.info(f"File saved: {file_path}")
        
        # Process document
        documents = document_processor.process_document(file_path)
        chunks_created = len(documents)
        
        # Add to vector store
        vector_store = get_vector_store()
        added_ids = vector_store.add_documents(documents)
        documents_added = len(added_ids)
        
        logger.info(f"Processed {file.filename}: {chunks_created} chunks, {documents_added} added")
        
        return {
            "filename": file.filename,
            "chunks_created": chunks_created,
            "documents_added": documents_added,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Query the RAG system"""
    logger.info(f"Query received: {request.query[:100]}")
    
    try:
        if not request.query.strip():
            raise HTTPException(status_code=400, detail="Query cannot be empty")
        
        # Process query through RAG pipeline
        response = rag_pipeline.query(
            query=request.query,
            k=request.k,
            rewrite_query=request.rewrite_query
        )
        
        logger.info(f"Query processed successfully, retrieved {response['document_count']} documents")
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/batch-upload")
async def batch_upload(files: List[UploadFile] = File(...)):
    """Upload multiple documents"""
    logger.info(f"Batch upload requested for {len(files)} files")
    
    results = []
    
    for file in files:
        try:
            # Validate file
            if not file.filename:
                results.append({
                    "filename": "Unknown",
                    "status": "failed",
                    "reason": "No filename"
                })
                continue
            
            file_ext = file.filename.split(".")[-1].lower()
            if file_ext not in document_processor.supported_types:
                results.append({
                    "filename": file.filename,
                    "status": "failed",
                    "reason": f"Unsupported file type: {file_ext}"
                })
                continue
            
            # Save and process
            content = await file.read()
            file_path = os.path.join(UPLOAD_DIRECTORY, file.filename)
            with open(file_path, "wb") as f:
                f.write(content)
            
            documents = document_processor.process_document(file_path)
            chunks_created = len(documents)
            
            vector_store = get_vector_store()
            added_ids = vector_store.add_documents(documents)
            
            results.append({
                "filename": file.filename,
                "status": "success",
                "chunks_created": chunks_created,
                "documents_added": len(added_ids)
            })
            
            logger.info(f"Successfully processed {file.filename}")
        except Exception as e:
            logger.error(f"Error processing {file.filename}: {str(e)}")
            results.append({
                "filename": file.filename,
                "status": "failed",
                "reason": str(e)
            })
    
    return {
        "timestamp": datetime.now().isoformat(),
        "total_files": len(files),
        "results": results
    }


@app.delete("/clear-memory")
async def clear_memory():
    """Clear conversation memory"""
    logger.info("Clear memory requested")
    try:
        rag_pipeline.clear_memory()
        return {
            "status": "success",
            "message": "Conversation memory cleared",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error clearing memory: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversation-history")
async def get_conversation_history():
    """Get conversation history"""
    logger.info("Conversation history requested")
    try:
        history = rag_pipeline.get_conversation_history()
        return {
            "message_count": len(history),
            "history": [
                {
                    "type": message.type,
                    "content": message.content
                }
                for message in history
            ],
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting conversation history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= Error Handlers =============

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return {
        "detail": "Internal server error",
        "error": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else "Internal server error"
    }


# ============= Startup/Shutdown Events =============

@app.on_event("startup")
async def startup_event():
    """Initialize components on startup"""
    logger.info("Application startup")
    logger.info(f"Vector DB: {get_vector_store().store_type}")
    logger.info(f"LLM Model: {rag_pipeline.llm_model}")
    logger.info(f"Embedding Model: {rag_pipeline.embedding_manager.model}")
    logger.info(f"Documents in vector store: {get_vector_store().get_document_count()}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Application shutdown")


if __name__ == "__main__":
    logger.info(f"Starting RAG Chatbot API on {API_HOST}:{API_PORT}")
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=RELOAD_API,
        log_level=LOG_LEVEL.lower()
    )
