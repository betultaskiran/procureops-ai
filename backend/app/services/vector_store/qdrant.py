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
        Koleksiyon yoksa oluşturur.
        Bu genelde uygulamanın başlangıcında çağrılır.
        """
        # Koleksiyon var mı kontrol et
        exists = await self.client.collection_exists(collection_name=self.COLLECTION_NAME)
        
        if not exists:
            # Boyutu embedding provider'dan alıyoruz (Örn Gemini için 768)
            dimension = self.embedding_provider.dimension
            
            await self.client.create_collection(
                collection_name=self.COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=dimension,
                    distance=models.Distance.COSINE,
                )
            )

            # Metadata bazlı filtreleme için indeksler (Hız için)
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
        Metin parçalarını (chunks) alır, vektöre çevirir ve Qdrant'a yazar.
        """
        if not chunks:
            return

        # Vektörleri oluştur (Batch)
        embeddings = await self.embedding_provider.embed_batch(chunks)

        points = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
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
                    id=str(uuid.uuid4()),  # Qdrant için rastgele UUID
                    vector=embedding,
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
        Kullanıcının sorgusuna (query) en yakın belgeleri bulur.
        Sadece kullanıcının ait olduğu organizasyonun belgelerinde arama yapar.
        """
        # Sorguyu vektöre çevir
        query_vector = await self.embedding_provider.embed_text(query)

        # Filtre (Tenant izolasyonu)
        filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="organization_id",
                    match=models.MatchValue(value=str(organization_id))
                )
            ]
        )

        response = await self.client.query_points(
            collection_name=self.COLLECTION_NAME,
            query=query_vector,
            query_filter=filter,
            limit=limit,
            score_threshold=score_threshold
        )

        # Sadece payload'u döndür (metin ve diğer metadata'lar)
        return [hit.payload for hit in response.points]
