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

            # Metadata bazlı filtreleme için indeksler
            try:
                await self.client.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name="organization_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

            try:
                await self.client.create_payload_index(
                    collection_name=self.COLLECTION_NAME,
                    field_name="doc_id",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass

    async def delete_by_doc_id(self, doc_id: str, organization_id: str | None = None):
        """
        Belgeye ait tüm chunk ve vektörleri Qdrant'tan siler.
        """
        conditions = [
            models.FieldCondition(
                key="doc_id",
                match=models.MatchValue(value=str(doc_id))
            )
        ]
        if organization_id:
            conditions.append(
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(value=str(organization_id))
                )
            )

        await self.client.delete(
            collection_name=self.COLLECTION_NAME,
            points_selector=models.FilterSelector(
                filter=models.Filter(must=conditions)
            )
        )

    async def ingest_documents(
        self, 
        organization_id: str, 
        doc_id: str, 
        chunks: List[Any],
        metadata: Dict[str, Any] = None
    ):
        """
        Metin parçalarını (chunks - str veya dict) alır, vektöre çevirir (Dense + Sparse) ve Qdrant'a yazar.
        """
        if not chunks:
            return

        # 1. Metin listesini ayıkla (str veya dict uyumlu)
        texts = [c["text"] if isinstance(c, dict) else str(c) for c in chunks]

        # 2. Dense Vektörleri (Anlam) oluştur
        dense_embeddings = await self.embedding_provider.embed_batch(texts)
        
        # 3. Sparse Vektörleri (BM25 Kelime) oluştur
        from app.services.embeddings.sparse import SparseEmbeddingService
        sparse_service = SparseEmbeddingService()
        sparse_embeddings = sparse_service.embed_texts(texts)

        points = []
        for i, (item, text, d_emb, s_emb) in enumerate(zip(chunks, texts, dense_embeddings, sparse_embeddings)):
            payload = {
                "organization_id": str(organization_id),
                "doc_id": str(doc_id),
                "chunk_index": i,
                "text": text,
            }
            if metadata:
                payload.update(metadata)
            if isinstance(item, dict):
                for k in ("section_title", "page_number", "is_header"):
                    if k in item and item[k] is not None:
                        payload[k] = item[k]

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

        # 4. Dense ve Sparse aramayı birlikte yürüt
        candidate_map = {}

        # 4a. Dense Arama (Anlamsal Benzerlik - Cosine Score)
        dense_response = await self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_dense,
            using="text-dense",
            limit=max(limit * 3, 10),
            query_filter=filter,
        )

        for hit in dense_response.points:
            p = dict(hit.payload or {})
            dense_score = float(hit.score)
            p["dense_score"] = dense_score
            p["sparse_score"] = 0.0
            p["score"] = dense_score
            candidate_map[hit.id] = p

        # 4b. Sparse Arama (BM25 Tam Kelime Eşleşmesi)
        sparse_response = await self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=models.SparseVector(
                indices=query_sparse["indices"],
                values=query_sparse["values"]
            ),
            using="text-sparse",
            limit=max(limit * 3, 10),
            query_filter=filter,
        )

        for hit in sparse_response.points:
            sparse_score = float(hit.score)
            if hit.id in candidate_map:
                candidate_map[hit.id]["sparse_score"] = sparse_score
                # Kelime eşleşmesi takviyesi (BM25 > 1 ise en fazla +0.06 puan ekle)
                if sparse_score > 0.5:
                    candidate_map[hit.id]["score"] += min(0.06, max(0.0, sparse_score * 0.003))
            else:
                p = dict(hit.payload or {})
                p["dense_score"] = 0.0
                p["sparse_score"] = sparse_score
                # Sadece sparse ile bulunanlar için normalize taban puan
                p["score"] = 0.50 + min(0.15, max(0.0, sparse_score * 0.005))
                candidate_map[hit.id] = p

        # 5. Skorlara göre sırala
        sorted_results = sorted(
            candidate_map.values(),
            key=lambda x: x.get("score", 0.0),
            reverse=True
        )

        return sorted_results[:max(limit * 2, 10)]
