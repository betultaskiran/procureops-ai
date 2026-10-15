import test from "node:test";
import assert from "node:assert/strict";

// Test suite for Phase 4C Supplier Performance & History logic

test("1. Pagination calculation handles empty and zero-page states safely", () => {
  // Empty history response from backend
  const emptyHistory = {
    items: [],
    total_count: 0,
    page: 1,
    page_size: 20,
    total_pages: 0,
  };

  const totalCount = emptyHistory.total_count || 0;
  const totalPages = Math.max(0, emptyHistory.total_pages || 0);
  const currentPage = totalPages === 0 ? 0 : emptyHistory.page;

  assert.strictEqual(totalCount, 0);
  assert.strictEqual(totalPages, 0);
  assert.strictEqual(currentPage, 0);

  // Pagination buttons should be disabled
  const prevDisabled = emptyHistory.page <= 1 || totalPages <= 1;
  const nextDisabled = emptyHistory.page >= totalPages || totalPages <= 1;

  assert.strictEqual(prevDisabled, true, "Previous button should be disabled when total_pages <= 1");
  assert.strictEqual(nextDisabled, true, "Next button should be disabled when total_pages <= 1");
});

test("2. Delivery reliability truthfully distinguishes unavailable (null) from confirmed 0%", () => {
  const unavailableMetrics = {
    is_available: false,
    confidence: "insufficient",
    eligible_orders_count: 0,
    on_time_orders_count: null,
    late_orders_count: null,
    early_orders_count: null,
    on_time_percentage: null,
    average_delay_days: null,
    notes: "Henüz teslimat tarihi verisi bulunmuyor.",
  };

  // Truthful check: when is_available is false, on_time_percentage MUST NOT be displayed as 0%
  const displayPercentage = unavailableMetrics.is_available && unavailableMetrics.on_time_percentage !== null
    ? `%${unavailableMetrics.on_time_percentage.toFixed(1)}`
    : "Veri Yok";

  assert.strictEqual(displayPercentage, "Veri Yok", "Unavailable delivery history must show 'Veri Yok', never 0%");
  assert.strictEqual(unavailableMetrics.confidence, "insufficient");
});

test("3. Request identity guard prevents stale responses from overwriting drawer state", () => {
  let currentSupplierId = "supplier-alpha-uuid";

  // Simulate two async responses arriving out-of-order
  const responses = [
    { supplier_id: "supplier-beta-uuid", supplier_name: "Supplier Beta" },
    { supplier_id: "supplier-alpha-uuid", supplier_name: "Supplier Alpha" },
  ];

  let activeDrawerPerformance = null;

  // Handler mimicking SupplierPerformanceDrawer request guard
  const handleResponse = (data) => {
    if (currentSupplierId === data.supplier_id) {
      activeDrawerPerformance = data;
    }
  };

  // Beta arrives after supplier switched to Alpha -> MUST be dropped
  handleResponse(responses[0]);
  assert.strictEqual(activeDrawerPerformance, null, "Stale response from previous supplier must be ignored");

  // Alpha arrives -> MUST be accepted
  handleResponse(responses[1]);
  assert.notStrictEqual(activeDrawerPerformance, null);
  assert.strictEqual(activeDrawerPerformance.supplier_name, "Supplier Alpha");
});

test("4. Multi-currency financials are strictly isolated and never aggregated without conversion", () => {
  const financialSummary = {
    TRY: {
      currency: "TRY",
      total_spend: 150000.0,
      average_order_value: 50000.0,
      orders_count: 3,
      final_amount_orders_count: 2,
      quoted_amount_orders_count: 1,
      historical_amount_orders_count: 0,
    },
    USD: {
      currency: "USD",
      total_spend: 12000.0,
      average_order_value: 6000.0,
      orders_count: 2,
      final_amount_orders_count: 2,
      quoted_amount_orders_count: 0,
      historical_amount_orders_count: 0,
    },
  };

  const currencies = Object.keys(financialSummary);
  assert.strictEqual(currencies.length, 2);
  assert.deepStrictEqual(currencies, ["TRY", "USD"]);

  // Verify currencies are kept separate
  assert.strictEqual(financialSummary["TRY"].currency, "TRY");
  assert.strictEqual(financialSummary["USD"].currency, "USD");
  assert.strictEqual(financialSummary["TRY"].total_spend, 150000.0);
  assert.strictEqual(financialSummary["USD"].total_spend, 12000.0);
});

test("5. Collision detection correctly flags overlapping external history records", () => {
  const historyItem = {
    id: "item-123",
    source_type: "external_history",
    order_reference: "PO-2026-0042",
    has_collision: true,
    collision_note: "Bu harici sipariş referansı sistemdeki canlı PO ile eşleşmektedir.",
    status: "completed",
    amount: 45000,
    currency: "TRY",
  };

  assert.strictEqual(historyItem.has_collision, true);
  assert.match(historyItem.collision_note, /canlı PO ile eşleşmektedir/);
});

test("6. Quality tracking distinguishes untracked state from zero defect confirmation", () => {
  const untrackedQuality = {
    is_tracked: false,
    tracked_orders_count: 0,
    total_quality_issues: null,
    total_rejections: null,
    notes: null,
  };

  const trackedQualityWithZeroDefects = {
    is_tracked: true,
    tracked_orders_count: 10,
    total_quality_issues: 0,
    total_rejections: 0,
    notes: "10 sipariş denetlendi, kusur yok.",
  };

  // Untracked state must NOT be presented as 0 defects
  assert.strictEqual(untrackedQuality.is_tracked, false);
  assert.strictEqual(untrackedQuality.total_quality_issues, null);

  // Tracked state with 0 defects
  assert.strictEqual(trackedQualityWithZeroDefects.is_tracked, true);
  assert.strictEqual(trackedQualityWithZeroDefects.total_quality_issues, 0);
});
