"""
Example usage and testing script for the RAG pipeline
"""

import logging
import asyncio
import os
from pathlib import Path
from typing import List

from document_processor import DocumentProcessor
from rag_pipeline import get_rag_pipeline
from vector_store import get_vector_store
from embeddings import get_embedding_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


class RAGExample:
    """Example usage of RAG pipeline"""

    def __init__(self):
        self.doc_processor = DocumentProcessor()
        self.rag_pipeline = get_rag_pipeline()
        self.vector_store = get_vector_store()
        self.embedding_manager = get_embedding_manager()

    def example_1_basic_query(self):
        """Example 1: Basic query without documents"""
        logger.info("=" * 50)
        logger.info("Example 1: Basic Query (will fail gracefully)")
        logger.info("=" * 50)

        query = "What is machine learning?"
        logger.info(f"Query: {query}")

        try:
            response = self.rag_pipeline.query(query, k=3)
            logger.info(f"Answer: {response['answer']}")
            logger.info(f"Documents retrieved: {response['document_count']}")
        except Exception as e:
            logger.error(f"Error: {str(e)}")

    def example_2_document_processing(self):
        """Example 2: Load and process sample documents"""
        logger.info("=" * 50)
        logger.info("Example 2: Document Processing")
        logger.info("=" * 50)

        # Create sample documents
        sample_docs_dir = "./sample_documents"
        os.makedirs(sample_docs_dir, exist_ok=True)

        # Create a sample text file
        sample_text_path = os.path.join(sample_docs_dir, "sample.txt")
        with open(sample_text_path, "w") as f:
            f.write("""
Machine Learning Basics

Machine learning is a subset of artificial intelligence that enables systems 
to learn and improve from experience without being explicitly programmed.

Key Concepts:
1. Supervised Learning: Learning from labeled data
2. Unsupervised Learning: Learning patterns from unlabeled data
3. Reinforcement Learning: Learning through trial and error

Algorithms:
- Linear Regression: Used for predicting continuous values
- Logistic Regression: Used for classification problems
- Decision Trees: Tree-based models for classification and regression
- Random Forest: Ensemble method using multiple decision trees
- Neural Networks: Deep learning models inspired by biological neurons

Applications:
- Image recognition and computer vision
- Natural language processing
- Recommendation systems
- Fraud detection
- Autonomous vehicles

Best Practices:
- Clean and prepare your data
- Split data into training and testing sets
- Normalize features for better performance
- Validate your model with cross-validation
- Monitor for overfitting and underfitting
            """)

        logger.info(f"Created sample document: {sample_text_path}")

        # Process document
        logger.info("Processing document...")
        documents = self.doc_processor.process_document(sample_text_path)
        logger.info(f"Created {len(documents)} chunks from the document")

        # Add to vector store
        logger.info("Adding documents to vector store...")
        added_ids = self.vector_store.add_documents(documents)
        logger.info(f"Added {len(added_ids)} documents to vector store")

        # Show stats
        total_docs = self.vector_store.get_document_count()
        logger.info(f"Total documents in vector store: {total_docs}")

        return sample_docs_dir

    def example_3_retrieval(self):
        """Example 3: Document retrieval"""
        logger.info("=" * 50)
        logger.info("Example 3: Document Retrieval")
        logger.info("=" * 50)

        queries = [
            "What is machine learning?",
            "Tell me about neural networks",
            "How is data split in machine learning?",
        ]

        for query in queries:
            logger.info(f"\nQuery: {query}")
            documents = self.rag_pipeline.retrieve_documents(query, k=3)
            logger.info(f"Retrieved {len(documents)} documents")

            for i, (doc, score) in enumerate(documents, 1):
                logger.info(f"\nDocument {i} (Score: {score:.4f}):")
                logger.info(f"Source: {doc.metadata.get('source')}")
                logger.info(f"Content: {doc.page_content[:150]}...")

    def example_4_rag_query(self):
        """Example 4: Complete RAG query"""
        logger.info("=" * 50)
        logger.info("Example 4: Complete RAG Query")
        logger.info("=" * 50)

        queries = [
            "What are the key concepts in machine learning?",
            "Which algorithms are used for classification?",
            "What are the best practices in machine learning?",
        ]

        for query in queries:
            logger.info(f"\nQuery: {query}")

            response = self.rag_pipeline.query(query, k=3, rewrite_query=False)

            logger.info(f"\nAnswer:")
            logger.info(response['answer'])

            logger.info(f"\nMetadata:")
            logger.info(f"- Documents retrieved: {response['document_count']}")
            logger.info(f"- Timestamp: {response['timestamp']}")

            if response['retrieved_documents']:
                logger.info(f"\nRetrieved sources:")
                for doc_meta in response['retrieved_documents']:
                    logger.info(f"  - {doc_meta['source']} (Score: {doc_meta['similarity_score']:.4f})")

    def example_5_embedding_test(self):
        """Example 5: Test embedding functionality"""
        logger.info("=" * 50)
        logger.info("Example 5: Embedding Test")
        logger.info("=" * 50)

        texts = [
            "Machine learning is a subset of AI",
            "Python is a programming language",
            "Neural networks are inspired by biological neurons"
        ]

        logger.info(f"Embedding {len(texts)} texts...")
        embeddings = self.embedding_manager.embed_texts(texts)

        logger.info(f"Embedding dimension: {len(embeddings[0])}")

        # Calculate similarity between first and third
        import numpy as np
        embedding_1 = np.array(embeddings[0])
        embedding_2 = np.array(embeddings[1])
        embedding_3 = np.array(embeddings[2])

        # Cosine similarity
        def cosine_similarity(a, b):
            return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_1_3 = cosine_similarity(embedding_1, embedding_3)
        sim_1_2 = cosine_similarity(embedding_1, embedding_2)

        logger.info(f"Similarity between ML and Neural Networks: {sim_1_3:.4f}")
        logger.info(f"Similarity between ML and Python: {sim_1_2:.4f}")

    def example_6_stats(self):
        """Example 6: Get system stats"""
        logger.info("=" * 50)
        logger.info("Example 6: System Statistics")
        logger.info("=" * 50)

        stats = self.rag_pipeline.get_stats()

        for key, value in stats.items():
            logger.info(f"{key}: {value}")

    def run_all_examples(self):
        """Run all examples"""
        logger.info("\n")
        logger.info("╔" + "=" * 60 + "╗")
        logger.info("║" + " " * 15 + "RAG PIPELINE EXAMPLES" + " " * 25 + "║")
        logger.info("╚" + "=" * 60 + "╝")

        self.example_1_basic_query()
        self.example_2_document_processing()
        self.example_3_retrieval()
        self.example_4_rag_query()
        self.example_5_embedding_test()
        self.example_6_stats()

        logger.info("\n")
        logger.info("=" * 60)
        logger.info("All examples completed!")
        logger.info("=" * 60)


if __name__ == "__main__":
    example = RAGExample()
    example.run_all_examples()
