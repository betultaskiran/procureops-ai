import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ
from app.models.quote import Quote


@pytest.mark.asyncio
async def test_create_and_list_suppliers():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_name = f"Test Supplier {uuid.uuid4().hex[:6]}"
        
        # 1. Create Supplier
        payload = {
            "name": unique_name,
            "email": f"info@{uuid.uuid4().hex[:6]}.com",
            "phone": "+90 555 123 4567",
            "city": "Istanbul",
            "country": "Turkey"
        }
        res = await client.post("/api/v1/suppliers", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["name"] == unique_name
        assert data["city"] == "Istanbul"
        assert "id" in data
        supplier_id = data["id"]

        # 2. Duplicate Detection
        dup_res = await client.post("/api/v1/suppliers", json={"name": unique_name.lower()})
        assert dup_res.status_code == 409
        assert "already exists" in dup_res.json()["detail"]

        # 3. List Suppliers
        list_res = await client.get("/api/v1/suppliers")
        assert list_res.status_code == 200
        suppliers = list_res.json()
        assert any(s["id"] == supplier_id for s in suppliers)


@pytest.mark.asyncio
async def test_rfq_quote_scoping_and_not_found():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create RFQ 1 and RFQ 2
        rfq1_res = await client.post("/api/v1/rfqs", json={"title": "RFQ Scope Test 1"})
        assert rfq1_res.status_code == 201
        rfq1_id = rfq1_res.json()["id"]

        rfq2_res = await client.post("/api/v1/rfqs", json={"title": "RFQ Scope Test 2"})
        assert rfq2_res.status_code == 201
        rfq2_id = rfq2_res.json()["id"]

        # Create a Supplier
        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Supplier {uuid.uuid4().hex[:6]}"})
        assert sup_res.status_code == 201
        supplier_id = sup_res.json()["id"]

        # Directly insert a Quote under RFQ 1 in the database
        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=uuid.UUID(rfq1_id),
                supplier_id=uuid.UUID(supplier_id),
                currency="TRY",
                subtotal=1000,
                total_price=1200,
            )
            session.add(quote)
            await session.commit()
            await session.refresh(quote)
            quote_id = str(quote.id)

        # Correct RFQ -> Quote found
        get_res = await client.get(f"/api/v1/rfqs/{rfq1_id}/quotes/{quote_id}")
        assert get_res.status_code == 200
        assert get_res.json()["id"] == quote_id

        # Wrong RFQ -> Quote NOT found (404)
        wrong_res = await client.get(f"/api/v1/rfqs/{rfq2_id}/quotes/{quote_id}")
        assert wrong_res.status_code == 404
        assert "not found under RFQ" in wrong_res.json()["detail"]
