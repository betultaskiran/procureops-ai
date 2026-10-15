import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization

import uuid

@pytest.fixture
async def setup_org():
    async with AsyncSessionLocal() as db:
        unique_slug = f"test-org-{uuid.uuid4().hex[:8]}"
        org = Organization(name="Test Org", slug=unique_slug)
        db.add(org)
        await db.commit()
        await db.refresh(org)
        yield org
        await db.delete(org)
        await db.commit()

from tests.auth_helper import create_test_auth_context
from app.models.user import UserRole

@pytest.mark.asyncio
async def test_create_and_read_rfq_with_items(setup_org):
    auth = await create_test_auth_context(role=UserRole.ADMIN, org_id=setup_org.id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Create RFQ
        req_data = {
            "title": "Test RFQ with Items",
            "description": "We need new servers",
            "budget": 50000.0,
            "max_delivery_days": 15,
            "min_warranty_months": 24,
            "payment_terms": "net-30",
            "items": [
                {
                    "description": "Server Type A",
                    "quantity": 5,
                    "unit": "Adet"
                },
                {
                    "description": "Server Type B",
                    "quantity": 2,
                    "unit": "Adet"
                }
            ]
        }
        response = await ac.post("/api/v1/rfqs", json=req_data, headers=auth.headers)
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Test RFQ with Items"
        assert data["budget"] == 50000.0
        assert len(data["items"]) == 2
        assert data["items"][0]["description"] == "Server Type A"
        rfq_id = data["id"]

        # Read RFQ back
        get_resp = await ac.get(f"/api/v1/rfqs/{rfq_id}", headers=auth.headers)
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["id"] == rfq_id
        assert get_data["max_delivery_days"] == 15
        assert len(get_data["items"]) == 2
        assert get_data["items"][1]["quantity"] == 2
