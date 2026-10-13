import os
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import AsyncSessionLocal
from app.models.organization import Organization
from app.models.supplier import Supplier
from app.models.rfq import RFQ, RFQItem, RFQStatus, QuoteDocument
from app.models.quote import Quote, QuoteItem
from app.models.analysis import Analysis, Approval, ApprovalStatus, Recommendation
from app.models.order import PurchaseOrder
from app.core.config import settings


@pytest.mark.asyncio
async def test_draft_rfq_deletion_success():
    """1. Silinmesi uygun bir taslak RFQ başarıyla silinebilmeli (200) ve ardından 404 dönmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create draft RFQ
        create_res = await client.post("/api/v1/rfqs", json={
            "title": f"Draft RFQ To Delete {uuid.uuid4().hex[:6]}",
            "budget": 100000.0,
            "items": [{"description": "Office Chairs", "quantity": 10, "unit": "Adet"}]
        })
        assert create_res.status_code == 201
        rfq_id = create_res.json()["id"]

        # Check metadata
        get_res = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_res.status_code == 200
        rfq_data = get_res.json()
        assert rfq_data["can_delete"] is True
        assert rfq_data["has_po"] is False
        assert rfq_data["quotes_count"] == 0

        # Delete RFQ
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "success"

        # Verify not found after deletion
        get_after = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_after.status_code == 404


@pytest.mark.asyncio
async def test_rfq_with_unapproved_quotes_and_files_cascade_deletion():
    """2. İlişkili teklif ve disk belgeleri olan RFQ silindiğinde cascade temizlik doğru uygulanmalı."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create RFQ
        rfq_res = await client.post("/api/v1/rfqs", json={
            "title": f"RFQ With Quotes {uuid.uuid4().hex[:6]}",
            "budget": 250000.0,
            "items": [{"description": "Monitors 27 inch", "quantity": 20, "unit": "Adet"}]
        })
        assert rfq_res.status_code == 201
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        # Create Supplier
        sup_res = await client.post("/api/v1/suppliers", json={
            "name": f"Supplier Tech {uuid.uuid4().hex[:6]}",
            "city": "Izmir"
        })
        assert sup_res.status_code == 201
        sup_id = uuid.UUID(sup_res.json()["id"])

        # Create a mock physical file on disk
        upload_dir = settings.UPLOAD_DIR
        os.makedirs(upload_dir, exist_ok=True)
        mock_file_name = f"test_quote_{uuid.uuid4().hex[:8]}.pdf"
        mock_file_path = os.path.join(upload_dir, mock_file_name)
        with open(mock_file_path, "wb") as f:
            f.write(b"%PDF-1.4 mock quote content for deletion test")

        assert os.path.exists(mock_file_path)

        async with AsyncSessionLocal() as session:
            # QuoteDocument
            quote_doc = QuoteDocument(
                rfq_id=rfq_id,
                supplier_id=sup_id,
                file_name=mock_file_name,
                file_path=mock_file_path,
                file_type="pdf",
                parse_status="completed"
            )
            session.add(quote_doc)
            await session.flush()

            # Quote
            quote = Quote(
                rfq_id=rfq_id,
                supplier_id=sup_id,
                quote_document_id=quote_doc.id,
                currency="TRY",
                subtotal=Decimal("200000.00"),
                vat_rate=Decimal("0.20"),
                vat_amount=Decimal("40000.00"),
                shipping_cost=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                other_costs=Decimal("0.00"),
                total_price=Decimal("240000.00"),
                delivery_days=10,
                warranty_months=24,
                extracted_supplier_name="Supplier Tech"
            )
            session.add(quote)
            await session.flush()

            # Quote Item
            q_item = QuoteItem(
                quote_id=quote.id,
                line_number=1,
                description="Monitors 27 inch",
                quantity=Decimal("20"),
                unit_price=Decimal("10000.00"),
                total_price=Decimal("200000.00")
            )
            session.add(q_item)
            await session.commit()
            quote_id = quote.id

        # Verify quote count is 1
        get_res = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_res.status_code == 200
        assert get_res.json()["quotes_count"] == 1

        # Delete RFQ
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_res.status_code == 200

        # DB verification: Quote should be gone
        get_q = await client.get(f"/api/v1/quotes/{quote_id}")
        assert get_q.status_code == 404

        # Disk verification: Physical file should be cleared from disk
        assert not os.path.exists(mock_file_path)


@pytest.mark.asyncio
async def test_rfq_deletion_blocked_when_po_or_approved():
    """3. PO oluşturulmuş veya onaylanmış RFQ silinemez (400 Bad Request)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create RFQ
        rfq_res = await client.post("/api/v1/rfqs", json={
            "title": f"Approved RFQ {uuid.uuid4().hex[:6]}",
            "budget": 500000.0,
            "items": [{"description": "Core Server", "quantity": 1, "unit": "Adet"}]
        })
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Core Sup {uuid.uuid4().hex[:6]}"})
        sup_id = uuid.UUID(sup_res.json()["id"])

        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=rfq_id,
                supplier_id=sup_id,
                currency="TRY",
                subtotal=Decimal("400000.00"),
                vat_rate=Decimal("0.20"),
                vat_amount=Decimal("80000.00"),
                shipping_cost=Decimal("0.00"),
                discount_amount=Decimal("0.00"),
                other_costs=Decimal("0.00"),
                total_price=Decimal("480000.00"),
                delivery_days=14,
                warranty_months=36
            )
            session.add(quote)
            await session.flush()

            analysis = Analysis(rfq_id=rfq_id, status="completed")
            session.add(analysis)
            await session.flush()

            approval = Approval(
                analysis_id=analysis.id,
                status=ApprovalStatus.APPROVED.value,
                selected_quote_id=quote.id
            )
            session.add(approval)
            await session.flush()

            po = PurchaseOrder(
                po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
                quote_id=quote.id,
                approval_id=approval.id,
                status="issued"
            )
            session.add(po)
            await session.commit()

        # Check metadata shows can_delete=False, has_po=True
        get_res = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_res.status_code == 200
        rfq_meta = get_res.json()
        assert rfq_meta["can_delete"] is False
        assert rfq_meta["has_po"] is True
        assert "Onaylanmış veya Satın Alma Siparişi (PO)" in rfq_meta["delete_block_reason"]

        # Attempt to delete RFQ
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_res.status_code == 400
        assert "Onaylanmış veya Satın Alma Siparişi (PO)" in del_res.json()["detail"]

        # Verify RFQ still exists
        get_still = await client.get(f"/api/v1/rfqs/{rfq_id}")
        assert get_still.status_code == 200


@pytest.mark.asyncio
async def test_unapproved_quote_deletion_success():
    """4. Silinmesi uygun bir teklif silinebilmeli (200), kalan teklifler korunmalı ve RFQ durumu güncellenmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rfq_res = await client.post("/api/v1/rfqs", json={
            "title": f"Quote Lifecycle RFQ {uuid.uuid4().hex[:6]}",
            "items": [{"description": "Laptops", "quantity": 5}]
        })
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        sup1_res = await client.post("/api/v1/suppliers", json={"name": f"Sup 1 {uuid.uuid4().hex[:6]}"})
        sup2_res = await client.post("/api/v1/suppliers", json={"name": f"Sup 2 {uuid.uuid4().hex[:6]}"})
        sup1_id = uuid.UUID(sup1_res.json()["id"])
        sup2_id = uuid.UUID(sup2_res.json()["id"])

        async with AsyncSessionLocal() as session:
            # Set RFQ status to collecting_quotes
            rfq_db = await session.get(RFQ, rfq_id)
            rfq_db.status = RFQStatus.COLLECTING_QUOTES.value

            q1 = Quote(
                rfq_id=rfq_id, supplier_id=sup1_id, currency="TRY",
                subtotal=Decimal("50000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("10000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("60000")
            )
            q2 = Quote(
                rfq_id=rfq_id, supplier_id=sup2_id, currency="TRY",
                subtotal=Decimal("55000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("11000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("66000")
            )
            session.add_all([q1, q2])
            await session.commit()
            q1_id = q1.id
            q2_id = q2.id

        # Verify both quotes listed
        quotes_res = await client.get(f"/api/v1/rfqs/{rfq_id}/quotes")
        assert quotes_res.status_code == 200
        assert len(quotes_res.json()) == 2
        assert quotes_res.json()[0]["can_delete"] is True

        # Delete Quote 1
        del_q1 = await client.delete(f"/api/v1/rfqs/{rfq_id}/quotes/{q1_id}")
        assert del_q1.status_code == 200

        # Quote 1 should be 404
        assert (await client.get(f"/api/v1/quotes/{q1_id}")).status_code == 404
        # Quote 2 should still be 200
        assert (await client.get(f"/api/v1/quotes/{q2_id}")).status_code == 200

        # Delete Quote 2 (last remaining quote)
        del_q2 = await client.delete(f"/api/v1/quotes/{q2_id}")
        assert del_q2.status_code == 200

        # When no quotes remain and RFQ was collecting_quotes, RFQ reverts to draft
        rfq_after = (await client.get(f"/api/v1/rfqs/{rfq_id}")).json()
        assert rfq_after["quotes_count"] == 0
        assert rfq_after["status"] == "draft"


@pytest.mark.asyncio
async def test_quote_deletion_blocked_when_used_in_po_or_approved_decision():
    """5. Analizde onaylanmış veya PO'ya bağlanmış teklif silinemez (400 Bad Request)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rfq_res = await client.post("/api/v1/rfqs", json={"title": "PO Quote Protect Test"})
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Sup PO {uuid.uuid4().hex[:6]}"})
        sup_id = uuid.UUID(sup_res.json()["id"])

        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=rfq_id, supplier_id=sup_id, currency="TRY",
                subtotal=Decimal("80000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("16000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("96000")
            )
            session.add(quote)
            await session.flush()

            analysis = Analysis(rfq_id=rfq_id, status="completed")
            session.add(analysis)
            await session.flush()

            approval = Approval(
                analysis_id=analysis.id,
                status=ApprovalStatus.APPROVED.value,
                selected_quote_id=quote.id
            )
            session.add(approval)
            await session.flush()

            po = PurchaseOrder(
                po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
                quote_id=quote.id,
                approval_id=approval.id,
                status="issued"
            )
            session.add(po)
            await session.commit()
            quote_id = quote.id

        # Verify quote metadata can_delete is False
        q_meta = (await client.get(f"/api/v1/quotes/{quote_id}")).json()
        assert q_meta["can_delete"] is False
        assert "Onaylanmış bir satın alma kararında" in q_meta["delete_block_reason"]

        # Attempt to delete quote
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_id}/quotes/{quote_id}")
        assert del_res.status_code == 400
        assert "Onaylanmış bir satın alma kararında" in del_res.json()["detail"]

        # Verify quote is preserved
        assert (await client.get(f"/api/v1/quotes/{quote_id}")).status_code == 200


@pytest.mark.asyncio
async def test_unauthorized_tenant_deletion_attempt():
    """6. Yetkisiz organizasyon ID ile silme isteği 403 Forbidden dönmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rfq_res = await client.post("/api/v1/rfqs", json={"title": "Tenant Auth RFQ"})
        rfq_id = rfq_res.json()["id"]

        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Tenant Sup {uuid.uuid4().hex[:6]}"})
        sup_id = uuid.UUID(sup_res.json()["id"])

        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=uuid.UUID(rfq_id), supplier_id=sup_id, currency="TRY",
                subtotal=Decimal("10000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("2000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("12000")
            )
            session.add(quote)
            await session.commit()
            quote_id = quote.id

        different_org = uuid.uuid4()

        # Delete RFQ with mismatched organization_id -> 403
        del_rfq_unauth = await client.delete(f"/api/v1/rfqs/{rfq_id}?organization_id={different_org}")
        assert del_rfq_unauth.status_code == 403

        # Delete Quote with mismatched organization_id -> 403
        del_q_unauth = await client.delete(f"/api/v1/rfqs/{rfq_id}/quotes/{quote_id}?organization_id={different_org}")
        assert del_q_unauth.status_code == 403


@pytest.mark.asyncio
async def test_repeated_deletion_attempt_returns_404():
    """7. Tekrarlı silme isteği veri tutarsızlığı oluşturmamalı, 404 dönmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create draft RFQ
        rfq_res = await client.post("/api/v1/rfqs", json={"title": "Idempotent Delete RFQ"})
        rfq_id = rfq_res.json()["id"]

        # First delete -> 200
        del_1 = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_1.status_code == 200

        # Repeated delete -> 404
        del_2 = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_2.status_code == 404


@pytest.mark.asyncio
async def test_rfq_list_reflects_metadata_and_updates_after_deletion():
    """8. RFQ listesi can_delete, quotes_count ve has_po alanlarını taşımalı, silme sonrası güncellenmeli."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create a unique RFQ
        title = f"List Update Test {uuid.uuid4().hex[:6]}"
        rfq_res = await client.post("/api/v1/rfqs", json={"title": title})
        rfq_id = rfq_res.json()["id"]

        # Verify present in list
        list_res = await client.get("/api/v1/rfqs")
        assert list_res.status_code == 200
        rfqs = list_res.json()
        target = next((r for r in rfqs if r["id"] == rfq_id), None)
        assert target is not None
        assert "can_delete" in target
        assert "quotes_count" in target
        assert "has_po" in target

        # Delete it
        del_res = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_res.status_code == 200

        # Verify absent from list
        list_after = await client.get("/api/v1/rfqs")
        rfqs_after = list_after.json()
        target_after = next((r for r in rfqs_after if r["id"] == rfq_id), None)
        assert target_after is None


@pytest.mark.asyncio
async def test_po_cancellation_preserves_records_and_logs_audit():
    """9. PO iptali finansal kaydı ve teklifi silmemeli, statüyü 'cancelled' yapmalı ve AuditEvent oluşturmalı."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Setup RFQ, Quote, Approval, PO
        rfq_res = await client.post("/api/v1/rfqs", json={"title": f"PO Cancel Test RFQ {uuid.uuid4().hex[:6]}"})
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Supplier POCancel {uuid.uuid4().hex[:6]}"})
        sup_id = uuid.UUID(sup_res.json()["id"])

        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=rfq_id, supplier_id=sup_id, currency="TRY",
                subtotal=Decimal("45000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("9000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("54000")
            )
            session.add(quote)
            await session.flush()

            analysis = Analysis(rfq_id=rfq_id, status="completed")
            session.add(analysis)
            await session.flush()

            approval = Approval(
                analysis_id=analysis.id, selected_quote_id=quote.id,
                status=ApprovalStatus.APPROVED.value
            )
            session.add(approval)
            await session.flush()

            po = PurchaseOrder(
                po_number=f"PO-TEST-{uuid.uuid4().hex[:6].upper()}",
                quote_id=quote.id,
                approval_id=approval.id,
                status="issued"
            )
            session.add(po)
            await session.commit()
            po_id = po.id
            quote_id = quote.id

        # 2. Hard deletion of RFQ must be strictly prohibited (HTTP 400)
        del_attempt = await client.delete(f"/api/v1/rfqs/{rfq_id}")
        assert del_attempt.status_code == 400

        # 3. Cancel the PO with a valid reason
        cancel_reason = "Tedarikçi taahhüt edilen teslimat süresine uyamayacağını bildirdi."
        cancel_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/purchase-orders/{po_id}/cancel",
            json={"reason": cancel_reason}
        )
        assert cancel_res.status_code == 200
        po_data = cancel_res.json()
        assert po_data["status"] == "cancelled"
        assert po_data["cancellation_reason"] == cancel_reason
        assert po_data["cancelled_at"] is not None

        # 4. Verify in DB: AuditEvent exists, PO & Quote exist (NEVER deleted)
        from app.models.audit import AuditEvent
        async with AsyncSessionLocal() as session:
            db_po = await session.get(PurchaseOrder, po_id)
            assert db_po is not None
            assert db_po.status == "cancelled"
            assert db_po.cancellation_reason == cancel_reason

            db_quote = await session.get(Quote, quote_id)
            assert db_quote is not None

            audit_query = await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "purchase_order",
                    AuditEvent.entity_id == po_id,
                    AuditEvent.event_type == "po_cancelled"
                )
            )
            audit = audit_query.scalar_one_or_none()
            assert audit is not None
            assert audit.payload["po_number"] == po_data["po_number"]
            assert audit.payload["reason"] == cancel_reason

        # 5. Repeated PO cancellation must return 400
        repeat_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/purchase-orders/{po_id}/cancel",
            json={"reason": "Tekrar iptal denemesi"}
        )
        assert repeat_res.status_code == 400
        assert "zaten iptal edilmiş" in repeat_res.json()["detail"]


@pytest.mark.asyncio
async def test_rfq_cancellation_flow_with_active_pos():
    """10. Aktif PO'su olan RFQ iptal edilirken aktif PO koruması ve toplu iptal akışı doğrulanmalı."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rfq_res = await client.post("/api/v1/rfqs", json={"title": f"RFQ Cancel Flow {uuid.uuid4().hex[:6]}"})
        rfq_id = uuid.UUID(rfq_res.json()["id"])

        sup_res = await client.post("/api/v1/suppliers", json={"name": f"Supplier RFQCancel {uuid.uuid4().hex[:6]}"})
        sup_id = uuid.UUID(sup_res.json()["id"])

        async with AsyncSessionLocal() as session:
            quote = Quote(
                rfq_id=rfq_id, supplier_id=sup_id, currency="TRY",
                subtotal=Decimal("70000"), vat_rate=Decimal("0.2"), vat_amount=Decimal("14000"),
                shipping_cost=Decimal("0"), discount_amount=Decimal("0"), other_costs=Decimal("0"),
                total_price=Decimal("84000")
            )
            session.add(quote)
            await session.flush()

            analysis = Analysis(rfq_id=rfq_id, status="completed")
            session.add(analysis)
            await session.flush()

            approval = Approval(analysis_id=analysis.id, selected_quote_id=quote.id, status=ApprovalStatus.APPROVED.value)
            session.add(approval)
            await session.flush()

            po = PurchaseOrder(po_number=f"PO-RFQ-{uuid.uuid4().hex[:6].upper()}", quote_id=quote.id, approval_id=approval.id, status="issued")
            session.add(po)
            await session.commit()
            po_id = po.id

        # 1. Trying to cancel RFQ with cancel_pos=False when active PO exists -> 400
        cancel_blocked = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Proje bütçesi iptal edildi.", "cancel_pos": False}
        )
        assert cancel_blocked.status_code == 400
        assert "aktif Satın Alma Siparişleri" in cancel_blocked.json()["detail"]

        # 2. Cancel RFQ with cancel_pos=True -> 200
        cancel_success = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Proje bütçesi iptal edildi.", "cancel_pos": True}
        )
        assert cancel_success.status_code == 200
        rfq_data = cancel_success.json()
        assert rfq_data["status"] == "cancelled"

        # 3. Verify PO is cancelled and audit records exist
        from app.models.audit import AuditEvent
        async with AsyncSessionLocal() as session:
            db_po = await session.get(PurchaseOrder, po_id)
            assert db_po is not None
            assert db_po.status == "cancelled"

            rfq_audit = await session.execute(
                select(AuditEvent).where(
                    AuditEvent.entity_type == "rfq",
                    AuditEvent.entity_id == rfq_id,
                    AuditEvent.event_type == "rfq_cancelled"
                )
            )
            assert rfq_audit.scalar_one_or_none() is not None

        # 4. Repeated RFQ cancel -> 400
        repeat_rfq_cancel = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Tekrar iptal denemesi", "cancel_pos": True}
        )
        assert repeat_rfq_cancel.status_code == 400


@pytest.mark.asyncio
async def test_rfq_archive_and_unarchive_flow():
    """11. RFQ arşivleme ve arşivden çıkarma, aktif liste filtrelemesi ve audit kaydı doğrulanmalı."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        unique_title = f"Archive Flow RFQ {uuid.uuid4().hex[:6]}"
        rfq_res = await client.post("/api/v1/rfqs", json={"title": unique_title})
        rfq_id = rfq_res.json()["id"]

        # 1. Archive RFQ
        archive_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/archive",
            json={"reason": "Yıllık temizlik arşivi"}
        )
        assert archive_res.status_code == 200
        assert archive_res.json()["is_archived"] is True

        # 2. Check default list excludes archived RFQ
        default_list = await client.get("/api/v1/rfqs")
        assert not any(r["id"] == rfq_id for r in default_list.json())

        # 3. Check archived_only=true includes this RFQ
        archived_list = await client.get("/api/v1/rfqs?archived_only=true")
        assert any(r["id"] == rfq_id for r in archived_list.json())

        # 4. Check include_archived=true includes this RFQ
        all_list = await client.get("/api/v1/rfqs?include_archived=true")
        assert any(r["id"] == rfq_id for r in all_list.json())

        # 5. Repeated archive -> 400
        repeat_archive = await client.post(f"/api/v1/rfqs/{rfq_id}/archive")
        assert repeat_archive.status_code == 400
        assert "zaten arşivlenmiş" in repeat_archive.json()["detail"]

        # 6. Unarchive RFQ
        unarchive_res = await client.post(f"/api/v1/rfqs/{rfq_id}/unarchive")
        assert unarchive_res.status_code == 200
        assert unarchive_res.json()["is_archived"] is False

        # 7. Check default list now includes it again
        restored_list = await client.get("/api/v1/rfqs")
        assert any(r["id"] == rfq_id for r in restored_list.json())


@pytest.mark.asyncio
async def test_cancellation_validation_and_multi_tenant_protection():
    """12. İptal işlemlerinde gerekçe validasyonu (min 3 karakter) ve tenant izolasyonu doğrulanmalı."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        rfq_res = await client.post("/api/v1/rfqs", json={"title": f"Tenant Check RFQ {uuid.uuid4().hex[:6]}"})
        rfq_id = rfq_res.json()["id"]

        # Empty reason -> 400
        empty_reason_res = await client.post(f"/api/v1/rfqs/{rfq_id}/cancel", json={"reason": "  "})
        assert empty_reason_res.status_code == 400
        assert "en az 3 karakter" in empty_reason_res.json()["detail"]

        # Different tenant org ID -> 403
        fake_org = str(uuid.uuid4())
        diff_tenant_res = await client.post(
            f"/api/v1/rfqs/{rfq_id}/cancel",
            json={"reason": "Geçerli gerekçe", "organization_id": fake_org}
        )
        assert diff_tenant_res.status_code == 403
        assert "Bu organizasyona ait olmayan" in diff_tenant_res.json()["detail"]

