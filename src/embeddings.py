# src/embeddings.py

import os
import requests
from typing import List
from langchain.embeddings.base import Embeddings
from dotenv import load_dotenv
from src.config import Config

# Load environment variables
load_dotenv()

class MorphwareEmbeddings(Embeddings):
    """Custom embeddings class for Morphware API"""
    
    def __init__(self, api_base: str, model: str, api_key: str):
        self.api_base = api_base.rstrip('/')  # Remove trailing slash if present
        self.model = model
        self.api_key = api_key
        print(f"Initialized MorphwareEmbeddings with model: {model}")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts"""
        print(f"Embedding {len(texts)} chunks...")
        embeddings = []
        batch_size = 10  # Process 10 at a time
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            print(f"Processing batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
            batch_embeddings = [self.embed_query(text) for text in batch]
            embeddings.extend(batch_embeddings)
            
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        """Get embeddings for a single piece of text"""
        if not text.strip():
            raise ValueError("Empty text provided for embedding")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        payload = {
            "model": self.model,
            "input": text,
            "truncate": True,
            "options": {},
            "keep_alive": 0
        }

        try:
            # Use instance's api_base and ensure proper URL construction
            embed_url = "https://app.morphware.com/ollama/api/embed"
            response = requests.post(
                embed_url,
                headers=headers,
                json=payload,
                timeout=30  # Add timeout
            )
            response.raise_for_status()
            
            response_data = response.json()
            if not response_data:
                raise Exception("Empty response received")
                
            if 'embeddings' in response_data and len(response_data['embeddings']) > 0:
                return response_data['embeddings'][0]
            else:
                raise Exception(f"No embeddings found in response: {response_data}")
                
        except requests.exceptions.RequestException as e:
            print(f"API request failed: {str(e)}")
            print(f"Request URL: {embed_url}")
            print(f"Response status code: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"Response content: {response.text if 'response' in locals() else 'N/A'}")
            raise
        except Exception as e:
            print(f"Error processing embedding: {str(e)}")
            raise