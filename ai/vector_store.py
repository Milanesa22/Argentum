# modules/ai/vector_store.py

import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer
import os

VECTOR_DB_PATH = "aurelius_knowledge"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

class VectorStore:
    def __init__(self, db_path=VECTOR_DB_PATH):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="scraped_knowledge",
            embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(EMBEDDING_MODEL)
        )
        self.model = SentenceTransformer(EMBEDDING_MODEL)
    
    def add_document(self, doc_id, text, metadata=None):
        self.collection.add(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[doc_id]
        )
    
    def query(self, query_text, top_k=5):
        return self.collection.query(query_texts=[query_text], n_results=top_k)
    
    def all_documents(self):
        results = self.collection.get(include=["documents", "metadatas"])
        return results

vector_store = VectorStore()