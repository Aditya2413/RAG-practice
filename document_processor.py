"""
Document Processing Module
Handles multi-format document loading, parsing, and chunking
"""

import logging
from typing import List, Dict, Any
from pathlib import Path
import os

from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredWordDocumentLoader,
    UnstructuredPowerPointLoader,
    CSVLoader,
    UnstructuredHTMLLoader,
)
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    CharacterTextSplitter,
)
from langchain_core.documents import Document

from config import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    CHUNK_STRATEGY,
    SUPPORTED_DOCUMENT_TYPES,
)

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Handles document loading, parsing, and chunking
    Supports multiple file formats: PDF, TXT, DOCX, PPTX, CSV, HTML, etc.
    """

    def __init__(self):
        self.supported_types = SUPPORTED_DOCUMENT_TYPES
        self.chunk_size = CHUNK_SIZE
        self.chunk_overlap = CHUNK_OVERLAP
        self.chunk_strategy = CHUNK_STRATEGY
        self._setup_chunkers()

    def _setup_chunkers(self):
        """Initialize text splitters for different strategies"""
        if self.chunk_strategy == "recursive":
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separators=["\n\n", "\n", ". ", " ", ""],
                length_function=len,
            )
        elif self.chunk_strategy == "fixed":
            self.text_splitter = CharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                separator="\n",
            )
        else:
            # Default to recursive
            self.text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
            )

    def load_document(self, file_path: str) -> List[Document]:
        """
        Load a document based on its file type
        
        Args:
            file_path: Path to the document
            
        Returns:
            List of Document objects
        """
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower().lstrip(".")

        if file_ext not in self.supported_types:
            raise ValueError(f"Unsupported file type: {file_ext}")

        try:
            if file_ext == "pdf":
                return self._load_pdf(str(file_path))
            elif file_ext == "txt":
                return self._load_txt(str(file_path))
            elif file_ext == "docx":
                return self._load_docx(str(file_path))
            elif file_ext == "pptx":
                return self._load_pptx(str(file_path))
            elif file_ext == "csv":
                return self._load_csv(str(file_path))
            elif file_ext == "html":
                return self._load_html(str(file_path))
            else:
                logger.warning(f"No specific loader for {file_ext}, using text loader")
                return self._load_txt(str(file_path))
        except Exception as e:
            logger.error(f"Error loading document {file_path}: {str(e)}")
            raise

    def _load_pdf(self, file_path: str) -> List[Document]:
        """Load PDF documents"""
        logger.info(f"Loading PDF: {file_path}")
        loader = PyPDFLoader(file_path)
        documents = loader.load()
        
        # Add metadata
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "pdf"
        
        logger.info(f"Loaded {len(documents)} pages from PDF")
        return documents

    def _load_txt(self, file_path: str) -> List[Document]:
        """Load text documents"""
        logger.info(f"Loading TXT: {file_path}")
        loader = TextLoader(file_path, encoding="utf-8")
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "txt"
        
        return documents

    def _load_docx(self, file_path: str) -> List[Document]:
        """Load DOCX documents"""
        logger.info(f"Loading DOCX: {file_path}")
        loader = UnstructuredWordDocumentLoader(file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "docx"
        
        return documents

    def _load_pptx(self, file_path: str) -> List[Document]:
        """Load PowerPoint documents"""
        logger.info(f"Loading PPTX: {file_path}")
        loader = UnstructuredPowerPointLoader(file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "pptx"
        
        return documents

    def _load_csv(self, file_path: str) -> List[Document]:
        """Load CSV documents"""
        logger.info(f"Loading CSV: {file_path}")
        loader = CSVLoader(file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "csv"
        
        return documents

    def _load_html(self, file_path: str) -> List[Document]:
        """Load HTML documents"""
        logger.info(f"Loading HTML: {file_path}")
        loader = UnstructuredHTMLLoader(file_path)
        documents = loader.load()
        
        for doc in documents:
            doc.metadata["source"] = file_path
            doc.metadata["file_type"] = "html"
        
        return documents

    def chunk_documents(self, documents: List[Document]) -> List[Document]:
        """
        Split documents into chunks
        
        Args:
            documents: List of Document objects
            
        Returns:
            List of chunked Document objects
        """
        logger.info(f"Chunking {len(documents)} documents with strategy: {self.chunk_strategy}")
        
        chunked_docs = self.text_splitter.split_documents(documents)
        
        # Add chunk metadata
        for i, doc in enumerate(chunked_docs):
            doc.metadata["chunk_id"] = i
            if "chunk_index" not in doc.metadata:
                doc.metadata["chunk_index"] = i
        
        logger.info(f"Created {len(chunked_docs)} chunks from {len(documents)} documents")
        return chunked_docs

    def process_document(self, file_path: str) -> List[Document]:
        """
        Complete document processing pipeline: load -> chunk
        
        Args:
            file_path: Path to the document
            
        Returns:
            List of chunked Document objects
        """
        logger.info(f"Processing document: {file_path}")
        
        # Load document
        documents = self.load_document(file_path)
        
        # Chunk documents
        chunked_documents = self.chunk_documents(documents)
        
        logger.info(f"Successfully processed {file_path} into {len(chunked_documents)} chunks")
        return chunked_documents

    def process_batch(self, file_paths: List[str]) -> List[Document]:
        """
        Process multiple documents
        
        Args:
            file_paths: List of file paths
            
        Returns:
            Combined list of chunked documents
        """
        all_docs = []
        
        for file_path in file_paths:
            try:
                docs = self.process_document(file_path)
                all_docs.extend(docs)
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {str(e)}")
                continue
        
        logger.info(f"Processed {len(file_paths)} files into {len(all_docs)} total chunks")
        return all_docs
