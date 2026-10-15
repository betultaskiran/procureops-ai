import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.models.rfq import RFQStatus
from app.models.user import UserRole
from tests.auth_helper import create_test_auth_context


@pytest.mark.asyncio
async def test_rfq_pagination_basic_offset_and_limits():
    """Verify page, page_size, total_count, total_pages, and SQL offset behavior."""
    auth = await create_test_auth_context(role=UserRole.ADMIN, org_name="Pagination Basic Org")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tag = uuid.uuid4().hex[:8]
        # Create 15 RFQs with the tag
        created_ids = []
        for i in range(15):
            res = await client.post(
                "/api/v1/rfqs",
                json={
                    "title": f"Batch RFQ {tag} - {i:02d}",
                    "budget": 1000.0 * (i + 1),
                    "items": [{"description": f"Item {tag} {i}", "quantity": 1, "unit": "Adet"}]
                },
                headers=auth.headers,
            )
            assert res.status_code == 201
            created_ids.append(res.json()["id"])

        # Query page 1 with page_size=10
        p1_res = await client.get(f"/api/v1/rfqs?search={tag}&page=1&page_size=10", headers=auth.headers)
        assert p1_res.status_code == 200
        p1 = p1_res.json()
        assert p1["total_count"] == 15
        assert p1["page"] == 1
        assert p1["page_size"] == 10
        assert p1["total_pages"] == 2
        assert len(p1["items"]) == 10

        # Query page 2 with page_size=10
        p2_res = await client.get(f"/api/v1/rfqs?search={tag}&page=2&page_size=10", headers=auth.headers)
        assert p2_res.status_code == 200
        p2 = p2_res.json()
        assert p2["total_count"] == 15
        assert p2["page"] == 2
        assert p2["page_size"] == 10
        assert p2["total_pages"] == 2
        assert len(p2["items"]) == 5

        # Ensure no overlap between page 1 and page 2 items
        p1_ids = {item["id"] for item in p1["items"]}
        p2_ids = {item["id"] for item in p2["items"]}
        assert len(p1_ids.intersection(p2_ids)) == 0

        # Query page 1 with page_size=50 -> all 15 on single page
        p50_res = await client.get(f"/api/v1/rfqs?search={tag}&page=1&page_size=50", headers=auth.headers)
        assert p50_res.status_code == 200
        p50 = p50_res.json()
        assert p50["total_count"] == 15
        assert p50["page_size"] == 50
        assert p50["total_pages"] == 1
        assert len(p50["items"]) == 15


@pytest.mark.asyncio
async def test_rfq_pagination_search_filter():
    """Verify search filter matches title, description, and nested RFQ items."""
    auth = await create_test_auth_context(role=UserRole.ADMIN, org_name="Pagination Search Org")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_key = uuid.uuid4().hex[:8]

        # 1. Matches title
        r1 = await client.post(
            "/api/v1/rfqs",
            json={
                "title": f"Special Alpha Project {unique_key}",
                "description": "Standard procurement"
            },
            headers=auth.headers,
        )
        assert r1.status_code == 201

        # 2. Matches description
        r2 = await client.post(
            "/api/v1/rfqs",
            json={
                "title": f"Beta Project {unique_key}",
                "description": f"Targeting secret-keyword-{unique_key} in details"
            },
            headers=auth.headers,
        )
        assert r2.status_code == 201

        # 3. Matches item description
        r3 = await client.post(
            "/api/v1/rfqs",
            json={
                "title": f"Gamma Project {unique_key}",
                "items": [{"description": f"Industrial Widget-{unique_key}", "quantity": 5}]
            },
            headers=auth.headers,
        )
        assert r3.status_code == 201

        # Search by item keyword
        res_item = await client.get(f"/api/v1/rfqs?search=Widget-{unique_key}", headers=auth.headers)
        assert res_item.status_code == 200
        data_item = res_item.json()
        assert data_item["total_count"] == 1
        assert data_item["items"][0]["id"] == r3.json()["id"]

        # Search by description keyword
        res_desc = await client.get(f"/api/v1/rfqs?search=secret-keyword-{unique_key}", headers=auth.headers)
        assert res_desc.status_code == 200
        data_desc = res_desc.json()
        assert data_desc["total_count"] == 1
        assert data_desc["items"][0]["id"] == r2.json()["id"]

        # Search by general unique_key (all 3 should match)
        res_all = await client.get(f"/api/v1/rfqs?search={unique_key}", headers=auth.headers)
        assert res_all.status_code == 200
        assert res_all.json()["total_count"] == 3


@pytest.mark.asyncio
async def test_rfq_pagination_status_and_archive_filters():
    """Verify filtering by status, archived_only, and include_archived."""
    auth = await create_test_auth_context(role=UserRole.ADMIN, org_name="Pagination Archive Org")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tag = uuid.uuid4().hex[:8]

        # RFQ 1: draft
        r1 = await client.post("/api/v1/rfqs", json={"title": f"Status Draft {tag}"}, headers=auth.headers)
        r1_id = r1.json()["id"]

        # RFQ 2: draft then archived
        r2 = await client.post("/api/v1/rfqs", json={"title": f"Status Archived {tag}"}, headers=auth.headers)
        r2_id = r2.json()["id"]
        arc_res = await client.post(f"/api/v1/rfqs/{r2_id}/archive", headers=auth.headers)
        assert arc_res.status_code == 200

        # Query default (active only, excluding archived)
        def_res = await client.get(f"/api/v1/rfqs?search={tag}", headers=auth.headers)
        assert def_res.status_code == 200
        def_data = def_res.json()
        assert def_data["total_count"] == 1
        assert def_data["items"][0]["id"] == r1_id

        # Query archived_only=true
        arc_list_res = await client.get(f"/api/v1/rfqs?search={tag}&archived_only=true", headers=auth.headers)
        assert arc_list_res.status_code == 200
        arc_data = arc_list_res.json()
        assert arc_data["total_count"] == 1
        assert arc_data["items"][0]["id"] == r2_id

        # Query include_archived=true
        all_res = await client.get(f"/api/v1/rfqs?search={tag}&include_archived=true", headers=auth.headers)
        assert all_res.status_code == 200
        all_data = all_res.json()
        assert all_data["total_count"] == 2


@pytest.mark.asyncio
async def test_dashboard_recent_rfqs_limit_and_archive_filter():
    """Verify /recent-rfqs excludes archived RFQs and respects the limit."""
    auth = await create_test_auth_context(role=UserRole.ADMIN, org_name="Dashboard Recent Org")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tag = uuid.uuid4().hex[:8]
        # Create an RFQ and archive it
        r = await client.post("/api/v1/rfqs", json={"title": f"Recent Archived {tag}"}, headers=auth.headers)
        r_id = r.json()["id"]
        await client.post(f"/api/v1/rfqs/{r_id}/archive", headers=auth.headers)

        recent_res = await client.get("/api/v1/dashboard/recent-rfqs", headers=auth.headers)
        assert recent_res.status_code == 200
        recent_data = recent_res.json()
        assert isinstance(recent_data, list)
        assert len(recent_data) <= 10
        # Archived RFQ must not appear in recent list
        assert not any(item["id"] == r_id for item in recent_data)
