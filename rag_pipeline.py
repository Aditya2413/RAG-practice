"""
RAG Pipeline Module
Core RAG logic combining document retrieval and LLM generation
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_groq import ChatGroq

from config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    OPENAI_API_KEY,
    GROQ_API_KEY,
    TOP_K,
    ENABLE_QUERY_REWRITING,
    MAX_MEMORY_MESSAGES,
)
from vector_store import get_vector_store
from embeddings import get_embedding_manager

logger = logging.getLogger(__name__)

# Default prompt template for RAG
DEFAULT_RAG_PROMPT = """Use the following pieces of context to answer the question at the end. 
If you don't know the answer, just say that you don't know, don't try to make up an answer.

Context:
{context}

Question: {question}

Answer:"""

class RAGPipeline:
    """
    Main RAG Pipeline class
    Combines document retrieval and LLM generation
    """

    def __init__(
        self,
        llm_provider: str = LLM_PROVIDER,
        llm_model: str = LLM_MODEL,
        prompt_template: Optional[str] = None,
        enable_memory: bool = True,
    ):
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.vector_store = get_vector_store()
        self.embedding_manager = get_embedding_manager()
        
        # Initialize LLM
        self._init_llm()
        
        # Initialize prompt template
        self.prompt_template = prompt_template or DEFAULT_RAG_PROMPT
        
        # Initialize memory for conversation
        self.memory = None
        self.max_memory_messages = MAX_MEMORY_MESSAGES
        if enable_memory:
            self.memory = InMemoryChatMessageHistory()
        
        logger.info(f"RAG Pipeline initialized with LLM: {llm_model}")

    def _init_llm(self):
        """Initialize the LLM"""
        if self.llm_provider == "openai":
            self.llm = ChatOpenAI(
                model=self.llm_model,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                api_key=OPENAI_API_KEY,
            )
            logger.info(f"Initialized OpenAI LLM: {self.llm_model}")
        elif self.llm_provider == "Groq":
            self.llm = ChatGroq(
                model=self.llm_model,
                temperature=LLM_TEMPERATURE,
                max_tokens=LLM_MAX_TOKENS,
                api_key=GROQ_API_KEY,
            )
            logger.info(f"Initialized Groq LLM: {self.llm_model}")
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def _rewrite_query(self, query: str) -> str:
        """
        Rewrite query for better retrieval
        Enhances queries by adding context and clarity
        """
        if not ENABLE_QUERY_REWRITING:
            return query
        
        try:
            logger.debug(f"Rewriting query: {query}")
            
            rewrite_prompt = f"""Rewrite the following user query to make it clearer and more specific for document retrieval.
Keep it concise. Just provide the rewritten query.

Original query: {query}

Rewritten query:"""
            
            # Use invoke instead of predict
            response = self.llm.invoke(rewrite_prompt)
            rewritten = response.content
            logger.debug(f"Rewritten to: {rewritten}")
            
            return rewritten.strip()
        except Exception as e:
            logger.warning(f"Query rewriting failed: {str(e)}, using original query")
            return query

    def retrieve_documents(
        self, 
        query: str, 
        k: int = TOP_K,
        rewrite: bool = True
    ) -> List[Tuple[Document, float]]:
        """
        Retrieve relevant documents for a query
        
        Args:
            query: User query
            k: Number of documents to retrieve
            rewrite: Whether to rewrite query
            
        Returns:
            List of (Document, similarity_score) tuples
        """
        logger.info(f"Retrieving documents for query: {query[:100]}")
        
        # Rewrite query if enabled
        if rewrite:
            query = self._rewrite_query(query)
        
        # Retrieve from vector store
        results = self.vector_store.search(query, k=k)
        
        logger.info(f"Retrieved {len(results)} documents")
        return results

    def _format_documents(self, documents: List[Tuple[Document, float]]) -> Tuple[str, List[Dict[str, Any]]]:
        """Format retrieved documents for prompt and metadata"""
        formatted_docs = []
        metadata_list = []
        
        for doc, score in documents:
            formatted_docs.append(f"Source: {doc.metadata.get('source', 'Unknown')}\n{doc.page_content}")
            
            metadata = {
                "source": doc.metadata.get("source"),
                "similarity_score": float(score),
                "file_type": doc.metadata.get("file_type", "unknown"),
                "chunk_id": doc.metadata.get("chunk_id"),
            }
            metadata_list.append(metadata)
        
        context = "\n\n---\n\n".join(formatted_docs)
        return context, metadata_list

    def _trim_memory(self):
        """Trim memory to keep only last MAX_MEMORY_MESSAGES messages"""
        if self.memory:
            messages = self.memory.messages
            if len(messages) > self.max_memory_messages * 2:  # *2 for user+ai pairs
                # Keep only the last MAX_MEMORY_MESSAGES pairs
                self.memory.clear()
                for msg in messages[-(self.max_memory_messages * 2):]:
                    self.memory.add_message(msg)

    def generate_response(
        self,
        query: str,
        documents: List[Tuple[Document, float]],
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generate response using LLM with retrieved documents
        
        Args:
            query: User query
            documents: Retrieved documents
            system_prompt: Custom system prompt
            
        Returns:
            Response dictionary with answer and metadata
        """
        logger.info("Generating response")
        
        # Format documents
        context, metadata_list = self._format_documents(documents)
        
        # Build prompt
        if system_prompt:
            prompt = system_prompt.format(context=context, question=query)
        else:
            prompt = self.prompt_template.format(context=context, question=query)
        
        try:
            # Generate answer using invoke
            response = self.llm.invoke(prompt)
            answer = response.content
            
            logger.debug(f"Generated response: {answer[:100]}...")
            
            # Add to memory if enabled
            if self.memory:
                self.memory.add_message(HumanMessage(content=query))
                self.memory.add_message(AIMessage(content=answer))
                self._trim_memory()
            
            return {
                "answer": answer.strip(),
                "query": query,
                "retrieved_documents": metadata_list,
                "timestamp": datetime.now().isoformat(),
                "document_count": len(documents),
            }
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            raise

    def query(
        self,
        query: str,
        k: int = TOP_K,
        rewrite_query: bool = True,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Complete RAG pipeline: retrieve and generate
        
        Args:
            query: User query
            k: Number of documents to retrieve
            rewrite_query: Whether to rewrite query for better retrieval
            system_prompt: Custom system prompt
            
        Returns:
            Complete response with answer and metadata
        """
        logger.info(f"Processing query: {query[:100]}")
        
        try:
            # Retrieve documents
            documents = self.retrieve_documents(query, k=k, rewrite=rewrite_query)
            
            if not documents:
                logger.warning("No documents retrieved, returning empty response")
                return {
                    "answer": "I couldn't find any relevant information in the knowledge base.",
                    "query": query,
                    "retrieved_documents": [],
                    "timestamp": datetime.now().isoformat(),
                    "document_count": 0,
                }
            
            # Generate response
            response = self.generate_response(query, documents, system_prompt)
            
            logger.info("Query processing completed successfully")
            return response
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            raise

    def get_conversation_history(self) -> List[BaseMessage]:
        """Get conversation history from memory"""
        if self.memory:
            return self.memory.messages
        return []

    def clear_memory(self):
        """Clear conversation memory"""
        if self.memory:
            self.memory.clear()
            logger.info("Conversation memory cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get RAG pipeline statistics"""
        return {
            "llm_model": self.llm_model,
            "vector_db_type": self.vector_store.store_type,
            "embedding_model": self.embedding_manager.model,
            "embedding_dimension": self.embedding_manager.get_dimension(),
            "total_documents": self.vector_store.get_document_count(),
            "memory_enabled": self.memory is not None,
            "query_rewriting_enabled": ENABLE_QUERY_REWRITING,
        }

# Global RAG pipeline instance
_rag_pipeline: Optional[RAGPipeline] = None

def get_rag_pipeline() -> RAGPipeline:
    """Get or create RAG pipeline singleton"""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline()
    return _rag_pipeline
