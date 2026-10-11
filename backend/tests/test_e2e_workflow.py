import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ, RFQItem
from app.models.quote import Quote, QuoteItem


@pytest.mark.asyncio
async def test_end_to_end_rfq_and_multi_quote_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        
        # 1. Create RFQ with two RFQItems and commercial conditions
        rfq_payload = {
            "title": f"Procurement Request {uuid.uuid4().hex[:6]}",
            "description": "High-performance compute clusters and networking hardware",
            "budget": 750000.0,
            "max_delivery_days": 20,
            "min_warranty_months": 36,
            "payment_terms": "net-30",
            "items": [
                {"description": "Enterprise Server Node", "quantity": 10, "unit": "Unit"},
                {"description": "100GbE Managed Switch", "quantity": 2, "unit": "Unit"}
            ]
        }
        create_rfq_res = await client.post("/api/v1/rfqs", json=rfq_payload)
        assert create_rfq_res.status_code == 201, create_rfq_res.text
        rfq_data = create_rfq_res.json()
        rfq_id = rfq_data["id"]
        assert len(rfq_data["items"]) == 2
        assert rfq_data["budget"] == 750000.0

        # Verify persistence after reload
        get_rfq_res = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_rfq_res.status_code == 200
        saved_rfq = get_rfq_res.json()
        assert len(saved_rfq["items"]) == 2
        assert saved_rfq["items"][0]["description"] == "Enterprise Server Node"

        # 2. Get or create Supplier 1 (e.g. DEF Elektronik)
        sup1_res = await client.post("/api/v1/suppliers", json={
            "name": f"DEF Elektronik {uuid.uuid4().hex[:6]}",
            "city": "Ankara"
        })
        assert sup1_res.status_code == 201
        sup1 = sup1_res.json()
        sup1_id = sup1["id"]

        # 3. Create Supplier 2 (different supplier)
        sup2_res = await client.post("/api/v1/suppliers", json={
            "name": f"Global Hardware Ltd {uuid.uuid4().hex[:6]}",
            "city": "Istanbul"
        })
        assert sup2_res.status_code == 201
        sup2 = sup2_res.json()
        sup2_id = sup2["id"]

        # 4. Attach two quotes under the same RFQ (one per supplier)
        async with AsyncSessionLocal() as session:
            quote1 = Quote(
                rfq_id=uuid.UUID(rfq_id),
                supplier_id=uuid.UUID(sup1_id),
                currency="TRY",
                subtotal=Decimal("600000.00"),
                vat_rate=Decimal("0.20"),
                vat_amount=Decimal("120000.00"),
                shipping_cost=Decimal("0.00"),
                discount_amount=Decimal("20000.00"),
                other_costs=Decimal("0.00"),
                total_price=Decimal("700000.00"),
                delivery_days=15,
                warranty_months=36,
                payment_terms="net-30",
                extracted_supplier_name=sup1["name"]
            )
            session.add(quote1)
            await session.flush()

            # Quote 1 items
            q1_item = QuoteItem(
                quote_id=quote1.id,
                line_number=1,
                description="Enterprise Server Node",
                quantity=Decimal("10"),
                unit_price=Decimal("60000.00"),
                total_price=Decimal("600000.00")
            )
            session.add(q1_item)

            quote2 = Quote(
                rfq_id=uuid.UUID(rfq_id),
                supplier_id=uuid.UUID(sup2_id),
                currency="TRY",
                subtotal=Decimal("650000.00"),
                vat_rate=Decimal("0.20"),
                vat_amount=Decimal("130000.00"),
                shipping_cost=Decimal("5000.00"),
                discount_amount=Decimal("0.00"),
                other_costs=Decimal("0.00"),
                total_price=Decimal("785000.00"),
                delivery_days=12,
                warranty_months=48,
                payment_terms="net-15",
                extracted_supplier_name=sup2["name"]
            )
            session.add(quote2)
            await session.flush()

            q2_item = QuoteItem(
                quote_id=quote2.id,
                line_number=1,
                description="Enterprise Server Node Rev B",
                quantity=Decimal("10"),
                unit_price=Decimal("650000.00"),
                total_price=Decimal("650000.00")
            )
            session.add(q2_item)
            await session.commit()
            
            q1_id = str(quote1.id)
            q2_id = str(quote2.id)

        # 5. Verify listing quotes for RFQ returns both quotes with their suppliers
        list_quotes_res = await client.get(f"/api/v1/rfqs/{rfq_id}/quotes")
        assert list_quotes_res.status_code == 200
        quotes_list = list_quotes_res.json()
        assert len(quotes_list) == 2
        quote_ids = [q["id"] for q in quotes_list]
        assert q1_id in quote_ids
        assert q2_id in quote_ids

        # 6. Verify Quote 1 details
        q1_detail_res = await client.get(f"/api/v1/rfqs/{rfq_id}/quotes/{q1_id}")
        assert q1_detail_res.status_code == 200
        q1_detail = q1_detail_res.json()
        assert q1_detail["supplier_id"] == sup1_id
        assert q1_detail["supplier_name"] == sup1["name"]
        assert q1_detail["total_price"] == 700000.0
        assert q1_detail["delivery_days"] == 15

        # 7. Verify Quote 2 details
        q2_detail_res = await client.get(f"/api/v1/rfqs/{rfq_id}/quotes/{q2_id}")
        assert q2_detail_res.status_code == 200
        q2_detail = q2_detail_res.json()
        assert q2_detail["supplier_id"] == sup2_id
        assert q2_detail["supplier_name"] == sup2["name"]
        assert q2_detail["total_price"] == 785000.0
        assert q2_detail["delivery_days"] == 12

        # 8. Negative test: Quote cannot be fetched under another RFQ
        other_rfq_res = await client.post("/api/v1/rfqs", json={"title": "Other RFQ"})
        other_rfq_id = other_rfq_res.json()["id"]
        
        mismatch_res = await client.get(f"/api/v1/rfqs/{other_rfq_id}/quotes/{q1_id}")
        assert mismatch_res.status_code == 404
        assert "not found under RFQ" in mismatch_res.json()["detail"]
