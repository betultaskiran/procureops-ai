from fastembed import SparseTextEmbedding
from typing import List, Dict, Any

class SparseEmbeddingService:
    """
    BM25 (Sparse Vector) hesaplama servisi.
    Metinleri kelime frekanslarına (indices, values) çevirir.
    Qdrant hybrid search için gereklidir.
    """
    def __init__(self, model_name: str = "Qdrant/bm25"):
        # Model ilk çağrıldığında indirilir ve önbelleğe alınır.
        self.model = SparseTextEmbedding(model_name=model_name)

    def embed_texts(self, texts: List[str]) -> List[Dict[str, Any]]:
        """
        Metin listesini sparse vektörlere çevirir.
        Dönen format Qdrant'ın beklediği dict yapısındadır.
        """
        embeddings = list(self.model.embed(texts))
        result = []
        for emb in embeddings:
            result.append({
                "indices": emb.indices.tolist(),
                "values": emb.values.tolist()
            })
        return result
