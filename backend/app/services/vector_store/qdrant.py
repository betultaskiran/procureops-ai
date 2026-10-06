"""
app/services/vector_store/qdrant.py

Qdrant Vector Database bağlantısı ve operasyonları.
Metin parçalarını (chunks), onlara karşılık gelen vektörleri (embeddings) ve
metadata'ları (rfq_id, doc_id) kaydetmek ve aramak için kullanılır.
"""

import uuid
from typing import List, Dict, Any
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.core.config import settings
from app.services.embeddings import get_embedding_provider


class QdrantService:
    """
    Qdrant ile etkileşime giren servis.
    Koleksiyon: "knowledge_base"
    """

    COLLECTION_NAME = "knowledge_base"

    def __init__(self):
        # Async istemci oluştur
        # url örneği: http://qdrant:6333
        url = f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        self.client = AsyncQdrantClient(url=url)
        self.embedding_provider = get_embedding_provider()

    async def initialize_collection(self):
        """
        Koleksiyon yoksa oluşturur. Hybrid Search için hem Dense hem de Sparse vektör yapılandırır.
        """
        exists = await self.client.collection_exists(collection_name=self.COLLECTION_NAME)
        
        if not exists:
            dimension = self.embedding_provider.dimension
            
            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                # Çoklu vektör (Named Vectors) kullanıyoruz. 
                # Biri "text-dense" (Gemini Anlamsal), diğeri "text-sparse" (BM25 Kelime)
                vectors_config={
                    "text-dense": models.VectorParams(
                        size=dimension,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "text-sparse": models.SparseVectorParams(
                        modifier=models.Modifier.IDF
                    )
                }
            )

            # Metadata bazlı filtreleme için indeks
            await self.client.create_payload_index(
                collection_name=self.COLLECTION_NAME,
                field_name="organization_id",
                field_schema=models.PayloadSchemaType.KEYWORD,
            )

    async def ingest_documents(
        self, 
        organization_id: str, 
        doc_id: str, 
        chunks: List[str],
        metadata: Dict[str, Any] = None
    ):
        """
        Metin parçalarını (chunks) alır, vektöre çevirir (Dense + Sparse) ve Qdrant'a yazar.
        """
        if not chunks:
            return

        # 1. Dense Vektörleri (Anlam) oluştur
        dense_embeddings = await self.embedding_provider.embed_batch(chunks)
        
        # 2. Sparse Vektörleri (BM25 Kelime) oluştur
        from app.services.embeddings.sparse import SparseEmbeddingService
        sparse_service = SparseEmbeddingService()
        sparse_embeddings = sparse_service.embed_texts(chunks)

        points = []
        for i, (chunk, d_emb, s_emb) in enumerate(zip(chunks, dense_embeddings, sparse_embeddings)):
            payload = {
                "organization_id": str(organization_id),
                "doc_id": str(doc_id),
                "chunk_index": i,
                "text": chunk,
            }
            if metadata:
                payload.update(metadata)

            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),
                    # Named vectors kullanıyoruz
                    vector={
                        "text-dense": d_emb,
                        "text-sparse": models.SparseVector(
                            indices=s_emb["indices"],
                            values=s_emb["values"]
                        )
                    },
                    payload=payload
                )
            )

        # Qdrant'a yükle (Upsert)
        await self.client.upsert(
            collection_name=self.COLLECTION_NAME,
            points=points
        )

    async def search(
        self, 
        organization_id: str, 
        query: str, 
        limit: int = 5,
        score_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Kullanıcının sorgusuna en yakın belgeleri bulur.
        Dense (Anlam) ve Sparse (Kelime) vektörleri aynı anda arar (Hybrid Search)
        ve Reciprocal Rank Fusion (RRF) ile sonuçları birleştirir.
        """
        # 1. Sorguyu Dense Vektöre Çevir
        query_dense = await self.embedding_provider.embed_text(query)

        # 2. Sorguyu Sparse Vektöre Çevir
        from app.services.embeddings.sparse import SparseEmbeddingService
        sparse_service = SparseEmbeddingService()
        query_sparse = sparse_service.embed_texts([query])[0]

        # 3. Filtre (Tenant izolasyonu)
        filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(value=str(organization_id))
                )
            ]
        )

        # 4. Hybrid Search (RRF)
        response = await self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using="text-dense",
                    limit=limit * 2,
                    filter=filter
                ),
                models.Prefetch(
                    query=models.SparseVector(
                        indices=query_sparse["indices"],
                        values=query_sparse["values"]
                    ),
                    using="text-sparse",
                    limit=limit * 2,
                    filter=filter
                )
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit
        )

        # Sadece payload'u döndür
        return [hit.payload for hit in response.points]
