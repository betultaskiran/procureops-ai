"use client";

import React, { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { portalApi } from "@/lib/api/portal";
import {
  PortalRFQResponse,
  PortalQuoteSubmitRequest,
  PortalQuoteItemSubmit,
} from "@/lib/api/types";
import { useTranslation } from "@/lib/i18n";
import { formatCurrency as fmtCurrency, formatDate as fmtDate, formatNumber as fmtNumber } from "@/lib/i18n/formatters";
import { LanguageToggle } from "@/components/language-toggle";
import { getLocalizedApiError } from "@/lib/i18n/apiErrorMap";

export default function SupplierPortalPage() {
  const params = useParams();
  const token = typeof params.token === "string" ? params.token : Array.isArray(params.token) ? params.token[0] : "";
  const { t, locale } = useTranslation();

  const [isLoading, setIsLoading] = useState(true);
  const [rfqData, setRfqData] = useState<PortalRFQResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Form states
  const [currency, setCurrency] = useState("TRY");
  const [subtotal, setSubtotal] = useState<string>("");
  const [vatRate, setVatRate] = useState<string>("0.20");
  const [vatAmount, setVatAmount] = useState<string>("");
  const [shippingCost, setShippingCost] = useState<string>("0");
  const [discountAmount, setDiscountAmount] = useState<string>("0");
  const [otherCosts, setOtherCosts] = useState<string>("0");
  const [deliveryDays, setDeliveryDays] = useState<string>("");
  const [warrantyMonths, setWarrantyMonths] = useState<string>("");
  const [paymentTerms, setPaymentTerms] = useState<string>("net-30");
  const [validUntil, setValidUntil] = useState<string>("");
  const [notes, setNotes] = useState<string>("");

  // Items pricing
  const [itemPrices, setItemPrices] = useState<Record<number, { unitPrice: string; totalPrice: string }>>({});

  // File upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploadingFile, setIsUploadingFile] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);

  // Submission state
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const fetchRfq = async () => {
    if (!token) {
      setLoadError(t("portal.error.missing_token"));
      setIsLoading(false);
      return;
    }
    try {
      setIsLoading(true);
      setLoadError(null);
      const data = await portalApi.getRfq(token);
      setRfqData(data);

      // Pre-fill if existing quote
      if (data.existing_quote) {
        const q = data.existing_quote;
        setCurrency(q.currency || "TRY");
        setSubtotal(String(q.subtotal));
        setVatRate(q.vat_rate !== null && q.vat_rate !== undefined ? String(q.vat_rate) : "0.20");
        setVatAmount(q.vat_amount !== null && q.vat_amount !== undefined ? String(q.vat_amount) : "");
        setShippingCost(q.shipping_cost ? String(q.shipping_cost) : "0");
        setDiscountAmount(q.discount_amount ? String(q.discount_amount) : "0");
        setOtherCosts(q.other_costs ? String(q.other_costs) : "0");
        setDeliveryDays(q.delivery_days ? String(q.delivery_days) : "");
        setWarrantyMonths(q.warranty_months !== null && q.warranty_months !== undefined ? String(q.warranty_months) : "");
        setPaymentTerms(q.payment_terms || "net-30");
        setValidUntil(q.valid_until || "");
        setNotes(q.notes || "");

        // Pre-fill item prices if present
        if (q.items && q.items.length > 0) {
          const pricesMap: Record<number, { unitPrice: string; totalPrice: string }> = {};
          q.items.forEach((it) => {
            pricesMap[it.line_number] = {
              unitPrice: String(it.unit_price),
              totalPrice: String(it.total_price),
            };
          });
          setItemPrices(pricesMap);
        }
      } else {
        // Defaults based on RFQ constraints
        if (data.max_delivery_days) setDeliveryDays(String(data.max_delivery_days));
        if (data.min_warranty_months) setWarrantyMonths(String(data.min_warranty_months));
        if (data.payment_terms) setPaymentTerms(data.payment_terms);
      }
    } catch (err: any) {
      setLoadError(getLocalizedApiError(err, locale));
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchRfq();
  }, [token]);

  // Derived grand total calculation
  const numSubtotal = parseFloat(subtotal) || 0;
  const numVatRate = parseFloat(vatRate) || 0;
  const numVatAmount = vatAmount !== "" ? parseFloat(vatAmount) || 0 : numSubtotal * numVatRate;
  const numShipping = parseFloat(shippingCost) || 0;
  const numDiscount = parseFloat(discountAmount) || 0;
  const numOther = parseFloat(otherCosts) || 0;
  const grandTotal = Math.max(0, numSubtotal + numVatAmount + numShipping + numOther - numDiscount);

  const handleItemPriceChange = (lineNumber: number, quantity: number, unitPriceStr: string) => {
    const uPrice = parseFloat(unitPriceStr) || 0;
    const tPrice = uPrice * quantity;
    const updated = {
      ...itemPrices,
      [lineNumber]: {
        unitPrice: unitPriceStr,
        totalPrice: tPrice.toFixed(2),
      },
    };
    setItemPrices(updated);

    // Auto-sum subtotal across all RFQ items if user fills them
    let sum = 0;
    rfqData?.items.forEach((it) => {
      const p = updated[it.line_number];
      if (p) sum += parseFloat(p.totalPrice) || 0;
    });
    if (sum > 0) {
      setSubtotal(sum.toFixed(2));
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    try {
      setIsUploadingFile(true);
      setUploadMessage(null);
      const res = await portalApi.uploadQuoteDocument(token, file);
      setUploadMessage(t("portal.form.file_upload_success", { name: res.file_name }));
    } catch (err: any) {
      setUploadMessage(t("portal.form.file_upload_error", { error: getLocalizedApiError(err, locale) }));
    } finally {
      setIsUploadingFile(false);
    }
  };

  const handleSubmitQuote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!numSubtotal || numSubtotal <= 0) {
      setSubmitError(t("portal.form.validation_subtotal_required"));
      return;
    }
    const days = parseInt(deliveryDays, 10);
    if (!days || days <= 0) {
      setSubmitError(t("portal.form.validation_delivery_required"));
      return;
    }

    try {
      setIsSubmitting(true);
      setSubmitError(null);
      setSubmitSuccess(null);

      // Prepare items list
      const itemsList: PortalQuoteItemSubmit[] = (rfqData?.items || []).map((it) => {
        const p = itemPrices[it.line_number];
        const uPrice = p ? parseFloat(p.unitPrice) || 0 : numSubtotal / (it.quantity || 1);
        const tPrice = p ? parseFloat(p.totalPrice) || 0 : numSubtotal;
        return {
          line_number: it.line_number,
          description: it.description,
          quantity: it.quantity,
          unit: it.unit || "Adet",
          unit_price: uPrice,
          total_price: tPrice,
        };
      });

      const payload: PortalQuoteSubmitRequest = {
        currency,
        subtotal: numSubtotal,
        vat_rate: numVatRate,
        vat_amount: vatAmount !== "" ? numVatAmount : undefined,
        shipping_cost: numShipping,
        discount_amount: numDiscount,
        other_costs: numOther,
        delivery_days: days,
        warranty_months: parseInt(warrantyMonths, 10) || 0,
        payment_terms: paymentTerms.trim() || undefined,
        valid_until: validUntil || undefined,
        notes: notes.trim() || undefined,
        items: itemsList.length > 0 ? itemsList : undefined,
      };

      const res = await portalApi.submitQuote(token, payload);
      setSubmitSuccess(res.message || t("portal.form.submit_success_default"));
      await fetchRfq();
    } catch (err: any) {
      setSubmitError(getLocalizedApiError(err, locale));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="text-center">
          <div className="w-10 h-10 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <h2 className="text-lg font-semibold text-slate-800">{t("portal.loading.title")}</h2>
          <p className="text-sm text-slate-500 mt-1">{t("portal.loading.desc")}</p>
        </div>
      </div>
    );
  }

  if (loadError || !rfqData) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6">
        <div className="max-w-md w-full bg-white rounded-xl shadow-lg border border-slate-200 p-8 text-center relative">
          <div className="absolute top-4 right-4">
            <LanguageToggle />
          </div>
          <div className="w-14 h-14 bg-red-100 text-red-600 rounded-full flex items-center justify-center mx-auto mb-4 text-2xl font-bold">
            !
          </div>
          <h1 className="text-xl font-bold text-slate-900 mb-2">{t("portal.error.access_denied_title")}</h1>
          <p className="text-sm text-slate-600 mb-6">{loadError || t("portal.error.default_desc")}</p>
          <div className="bg-slate-50 rounded-lg p-4 text-xs text-slate-500 text-left border border-slate-200">
            <p className="font-semibold mb-1">{t("portal.error.possible_reasons_title")}</p>
            <ul className="list-disc pl-4 space-y-1">
              <li>{t("portal.error.reason_expired")}</li>
              <li>{t("portal.error.reason_revoked")}</li>
              <li>{t("portal.error.reason_cancelled")}</li>
            </ul>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header Branding */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-blue-600 mb-1">
              <span className="w-2 h-2 rounded-full bg-blue-600" />
              {t("portal.header.badge", { org: rfqData.organization_name })}
            </div>
            <h1 className="text-2xl font-bold text-slate-900">{t("portal.header.title")}</h1>
            <p className="text-sm text-slate-600 mt-1">
              {t("portal.header.invited_supplier", { supplier: rfqData.supplier_name, email: rfqData.supplier_email })}
            </p>
          </div>
          <div className="flex flex-col items-start sm:items-end gap-2 border-t sm:border-t-0 pt-3 sm:pt-0 border-slate-100">
            <div className="flex items-center gap-2">
              <LanguageToggle />
              <span
                className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${
                  rfqData.can_submit
                    ? "bg-emerald-100 text-emerald-800 border border-emerald-200"
                    : "bg-amber-100 text-amber-800 border border-amber-200"
                }`}
              >
                {rfqData.can_submit ? t("portal.header.status_open") : t("portal.header.status_closed")}
              </span>
            </div>
            <div className="text-xs text-slate-500">
              {t("portal.header.link_expiry", { date: fmtDate(rfqData.expires_at, locale) })}
            </div>
          </div>
        </div>

        {/* Existing Quote Status Banner */}
        {rfqData.existing_quote && (
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5 flex items-start gap-4">
            <div className="p-2 bg-blue-100 text-blue-700 rounded-lg text-lg">✓</div>
            <div className="flex-1">
              <h3 className="text-sm font-bold text-blue-900">{t("portal.existing_quote.title")}</h3>
              <p className="text-xs text-blue-700 mt-1">
                {t("portal.existing_quote.last_updated", {
                  date: fmtDate(rfqData.existing_quote.created_at, locale),
                  amount: fmtCurrency(rfqData.existing_quote.total_price, rfqData.existing_quote.currency, locale)
                })}
              </p>
              <p className="text-xs text-blue-600 mt-1">
                {t("portal.existing_quote.notice")}
              </p>
            </div>
          </div>
        )}

        {/* RFQ Specifications Card */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="bg-slate-900 text-white px-6 py-4">
            <h2 className="text-lg font-bold">{rfqData.rfq_title}</h2>
            <p className="text-xs text-slate-300 mt-1">
              {t("portal.specifications.ref_code", { id: rfqData.rfq_id })}
            </p>
          </div>

          <div className="p-6 space-y-6">
            {rfqData.rfq_description && (
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  {t("portal.specifications.scope_title")}
                </h4>
                <p className="text-sm text-slate-700 bg-slate-50 p-4 rounded-lg border border-slate-200 whitespace-pre-wrap">
                  {rfqData.rfq_description}
                </p>
              </div>
            )}

            {/* Key Requirements Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 block">{t("portal.specifications.requested_qty")}</span>
                <span className="text-sm font-bold text-slate-900">
                  {rfqData.required_quantity 
                    ? t("portal.specifications.qty_unit", { qty: fmtNumber(rfqData.required_quantity, locale) }) 
                    : t("portal.specifications.per_specification")}
                </span>
              </div>
              <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 block">{t("portal.specifications.target_delivery")}</span>
                <span className="text-sm font-bold text-slate-900">
                  {rfqData.required_date ? fmtDate(rfqData.required_date, locale) : t("portal.specifications.open_date")}
                </span>
              </div>
              <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 block">{t("portal.specifications.max_delivery")}</span>
                <span className="text-sm font-bold text-slate-900">
                  {rfqData.max_delivery_days ? t("portal.specifications.days_unit", { days: rfqData.max_delivery_days }) : t("portal.specifications.not_specified")}
                </span>
              </div>
              <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200">
                <span className="text-xs text-slate-500 block">{t("portal.specifications.min_warranty")}</span>
                <span className="text-sm font-bold text-slate-900">
                  {rfqData.min_warranty_months ? t("portal.specifications.months_unit", { months: rfqData.min_warranty_months }) : t("portal.specifications.not_specified")}
                </span>
              </div>
            </div>

            {/* Items Table */}
            {rfqData.items && rfqData.items.length > 0 && (
              <div>
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">
                  {t("portal.specifications.items_title")}
                </h4>
                <div className="overflow-x-auto border border-slate-200 rounded-lg">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-100 text-slate-700 text-xs uppercase font-semibold">
                      <tr>
                        <th className="py-2.5 px-3 w-12 text-center">{t("portal.specifications.th_hash")}</th>
                        <th className="py-2.5 px-3">{t("portal.specifications.th_description")}</th>
                        <th className="py-2.5 px-3 w-28 text-right">{t("portal.specifications.th_quantity")}</th>
                        <th className="py-2.5 px-3 w-24">{t("portal.specifications.th_unit")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {rfqData.items.map((item) => (
                        <tr key={item.line_number} className="hover:bg-slate-50">
                          <td className="py-2 px-3 text-center text-xs text-slate-500">{item.line_number}</td>
                          <td className="py-2 px-3 font-medium text-slate-800">{item.description}</td>
                          <td className="py-2 px-3 text-right font-semibold text-slate-900">{fmtNumber(item.quantity, locale)}</td>
                          <td className="py-2 px-3 text-slate-600 text-xs">{item.unit || "Adet"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Quotation Submission Form */}
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="border-b border-slate-200 px-6 py-4 bg-slate-50 flex items-center justify-between">
            <h2 className="text-lg font-bold text-slate-900">
              {rfqData.existing_quote ? t("portal.form.title_update") : t("portal.form.title_new")}
            </h2>
            <span className="text-xs text-slate-500">{t("portal.form.all_fields_notice")}</span>
          </div>

          <form onSubmit={handleSubmitQuote} className="p-6 space-y-6">
            {submitSuccess && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm p-4 rounded-lg flex items-center justify-between">
                <span>✓ {submitSuccess}</span>
                <button type="button" onClick={() => setSubmitSuccess(null)} className="text-xs underline font-semibold">
                  {t("approvals_page.close")}
                </button>
              </div>
            )}

            {submitError && (
              <div className="bg-red-50 border border-red-200 text-red-800 text-sm p-4 rounded-lg">
                ⚠ {submitError}
              </div>
            )}

            {/* Financial Details */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.currency_label")}
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
                >
                  <option value="TRY">{t("portal.form.currency_options.try")}</option>
                  <option value="USD">{t("portal.form.currency_options.usd")}</option>
                  <option value="EUR">{t("portal.form.currency_options.eur")}</option>
                  <option value="GBP">{t("portal.form.currency_options.gbp")}</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.subtotal_label")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  required
                  placeholder="0.00"
                  value={subtotal}
                  onChange={(e) => setSubtotal(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.vat_rate_label")}
                </label>
                <select
                  value={vatRate}
                  onChange={(e) => {
                    setVatRate(e.target.value);
                    setVatAmount("");
                  }}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none bg-white"
                >
                  <option value="0.20">{t("portal.form.vat_options.standard_20")}</option>
                  <option value="0.10">{t("portal.form.vat_options.reduced_10")}</option>
                  <option value="0.01">{t("portal.form.vat_options.basic_1")}</option>
                  <option value="0.00">{t("portal.form.vat_options.exempt_0")}</option>
                </select>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.shipping_cost_label")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={shippingCost}
                  onChange={(e) => setShippingCost(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.discount_amount_label")}
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={discountAmount}
                  onChange={(e) => setDiscountAmount(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              {/* Grand Total Preview Card */}
              <div className="bg-slate-900 text-white rounded-lg p-3 flex flex-col justify-center">
                <span className="text-xs text-slate-400">
                  {t("portal.form.total_preview_label")}
                </span>
                <span className="text-lg font-bold text-emerald-400">
                  {fmtCurrency(grandTotal, currency, locale)}
                </span>
              </div>
            </div>

            {/* Commercial Conditions */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 border-t border-slate-200">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.delivery_days_label")}
                </label>
                <input
                  type="number"
                  required
                  min="1"
                  max="365"
                  placeholder={t("portal.form.delivery_days_placeholder")}
                  value={deliveryDays}
                  onChange={(e) => setDeliveryDays(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.warranty_months_label")}
                </label>
                <input
                  type="number"
                  required
                  min="0"
                  max="120"
                  placeholder={t("portal.form.warranty_months_placeholder")}
                  value={warrantyMonths}
                  onChange={(e) => setWarrantyMonths(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.payment_terms_label")}
                </label>
                <input
                  type="text"
                  required
                  placeholder={t("portal.form.payment_terms_placeholder")}
                  value={paymentTerms}
                  onChange={(e) => setPaymentTerms(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Validity and Notes */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.valid_until_label")}
                </label>
                <input
                  type="date"
                  value={validUntil}
                  onChange={(e) => setValidUntil(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  {t("portal.form.notes_label")}
                </label>
                <input
                  type="text"
                  placeholder={t("portal.form.notes_placeholder")}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Optional Quote Document Upload */}
            <div className="pt-4 border-t border-slate-200">
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                {t("portal.form.file_upload_label")}
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="file"
                  accept=".pdf,.xlsx,.png,.jpg"
                  onChange={handleFileUpload}
                  disabled={isUploadingFile}
                  className="text-xs text-slate-600 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-slate-100 file:text-slate-700 hover:file:bg-slate-200 cursor-pointer"
                />
                {isUploadingFile && <span className="text-xs text-blue-600 font-medium">{t("portal.form.file_upload_loading")}</span>}
              </div>
              {uploadMessage && (
                <p className={`text-xs mt-1.5 ${uploadMessage.includes("Error") || uploadMessage.includes("Hata") ? "text-red-600 font-semibold" : "text-emerald-600"}`}>
                  {uploadMessage}
                </p>
              )}
            </div>

            {/* Submit Action */}
            <div className="pt-6 border-t border-slate-200 flex items-center justify-end gap-4">
              <button
                type="submit"
                disabled={isSubmitting || !rfqData.can_submit}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white font-semibold px-6 py-2.5 rounded-lg text-sm shadow-sm transition-colors"
              >
                {isSubmitting 
                  ? t("portal.form.submit_btn_loading") 
                  : rfqData.existing_quote 
                  ? t("portal.form.submit_btn_update") 
                  : t("portal.form.submit_btn_new")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
