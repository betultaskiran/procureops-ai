"""
app/services/email/renderer.py

Email address validation and message rendering templates for RFQ invitations and PO notifications.
"""

import html
import re
import uuid
from datetime import date
from typing import Any

# RFC 5322 simplified email regex with strict CRLF injection protection
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


class EmailValidationError(ValueError):
    """Raised when an email address violates security or syntax rules."""
    pass


def validate_email_address(email: str) -> str:
    """
    Validates email format and strictly guards against CRLF / Header Injection attacks.
    """
    if not email:
        raise EmailValidationError("Recipient email cannot be empty.")

    # Guard against Header Injection
    if "\r" in email or "\n" in email or "%0a" in email.lower() or "%0d" in email.lower():
        raise EmailValidationError("Recipient email contains prohibited newline or control characters.")

    cleaned = email.strip()
    if len(cleaned) > 320:
        raise EmailValidationError("Recipient email exceeds maximum allowable length of 320 characters.")

    if not EMAIL_REGEX.match(cleaned):
        raise EmailValidationError(f"Invalid email address format: '{cleaned}'")

    return cleaned


def sanitize_header_value(value: str) -> str:
    """Strip newlines from headers to prevent header injection."""
    return value.replace("\r", " ").replace("\n", " ").strip()


def render_rfq_invitation(
    rfq_id: uuid.UUID,
    rfq_title: str,
    rfq_description: str | None,
    required_quantity: int | None,
    required_date: date | None,
    supplier_name: str,
    recipient_name: str | None,
    organization_name: str,
    app_base_url: str,
    custom_message: str | None = None,
) -> tuple[str, str, str]:
    """
    Renders (subject, text_body, html_body) for an RFQ invitation to a supplier.
    """
    subject = sanitize_header_value(f"[{organization_name}] Request for Quotation: {rfq_title}")

    greeting = f"Dear {recipient_name}," if recipient_name else f"Dear {supplier_name} Team,"
    clean_desc = rfq_description.strip() if rfq_description else "No additional description provided."
    qty_str = f"{required_quantity:,}" if required_quantity is not None else "As specified in requirements"
    deadline_str = required_date.strftime("%B %d, %Y") if required_date else "Open until fulfilled"
    rfq_link = f"{app_base_url.rstrip('/')}/dashboard/rfq/{rfq_id}"

    # Plain Text
    custom_text = f"\nNote from Procurement:\n{custom_message}\n" if custom_message else ""
    text_body = f"""{greeting}

You have been invited by {organization_name} to submit a quotation for the following Request for Quotation (RFQ):

Title: {rfq_title}
Reference ID: {rfq_id}
Required Quantity: {qty_str}
Response Deadline: {deadline_str}

RFQ Scope & Specifications:
{clean_desc}
{custom_text}
To review this procurement request and submit your formal quotation, please log in to the ProcureOps portal:
{rfq_link}

Best regards,
Procurement Team
{organization_name}
"""

    # Responsive HTML
    escaped_title = html.escape(rfq_title)
    escaped_org = html.escape(organization_name)
    escaped_greeting = html.escape(greeting)
    escaped_desc = html.escape(clean_desc).replace("\n", "<br/>")
    escaped_custom = (
        f"""<div style="background-color: #f1f5f9; border-left: 4px solid #3b82f6; padding: 12px; margin: 16px 0; border-radius: 4px;">
            <strong style="color: #1e293b;">Note from Procurement:</strong><br/>
            <p style="margin: 4px 0 0 0; color: #334155;">{html.escape(custom_message).replace(chr(10), '<br/>')}</p>
        </div>"""
        if custom_message
        else ""
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; line-height: 1.5; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; }}
    .header {{ border-bottom: 2px solid #3b82f6; padding-bottom: 12px; margin-bottom: 20px; }}
    .title {{ font-size: 20px; font-weight: bold; color: #0f172a; margin: 0; }}
    .meta-box {{ background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 16px; margin: 16px 0; }}
    .meta-row {{ margin-bottom: 8px; }}
    .meta-label {{ font-weight: 600; color: #475569; width: 150px; display: inline-block; }}
    .btn {{ display: inline-block; background-color: #2563eb; color: #ffffff !important; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 16px 0; }}
    .footer {{ font-size: 12px; color: #64748b; border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2 class="title">{escaped_org} — Request for Quotation</h2>
    </div>
    <p>{escaped_greeting}</p>
    <p>You have been invited by <strong>{escaped_org}</strong> to submit a quotation for the following RFQ:</p>
    
    <div class="meta-box">
      <div class="meta-row"><span class="meta-label">RFQ Title:</span> <strong>{escaped_title}</strong></div>
      <div class="meta-row"><span class="meta-label">Required Quantity:</span> {html.escape(qty_str)}</div>
      <div class="meta-row"><span class="meta-label">Response Deadline:</span> {html.escape(deadline_str)}</div>
      <div class="meta-row"><span class="meta-label">Reference ID:</span> <code>{rfq_id}</code></div>
    </div>

    <h4>Scope & Specifications</h4>
    <p style="color: #334155;">{escaped_desc}</p>

    {escaped_custom}

    <div style="text-align: center; margin: 24px 0;">
      <a href="{rfq_link}" class="btn">View RFQ & Submit Quote</a>
    </div>

    <div class="footer">
      <p>This invitation was generated automatically by ProcureOps AI on behalf of {escaped_org}.</p>
      <p>Direct link: <a href="{rfq_link}" style="color: #2563eb;">{rfq_link}</a></p>
    </div>
  </div>
</body>
</html>"""

    return subject, text_body, html_body


def render_po_notification(
    po_number: str,
    po_id: uuid.UUID,
    supplier_name: str,
    total_amount: str,
    currency: str,
    organization_name: str,
    app_base_url: str,
) -> tuple[str, str, str]:
    """
    Renders (subject, text_body, html_body) for a Purchase Order notification.
    """
    subject = sanitize_header_value(f"[{organization_name}] Official Purchase Order Issued: {po_number}")
    po_link = f"{app_base_url.rstrip('/')}/dashboard/orders"

    text_body = f"""Dear {supplier_name} Team,

An official Purchase Order has been issued by {organization_name}:

PO Number: {po_number}
Total Amount: {total_amount} {currency}
Order ID: {po_id}

Please confirm receipt of this purchase order and initiate fulfillment according to agreed delivery schedules.

Review Order Details:
{po_link}

Best regards,
Procurement & Finance Department
{organization_name}
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; }}
    .container {{ max-width: 600px; margin: 0 auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 8px; }}
    .header {{ border-bottom: 2px solid #10b981; padding-bottom: 12px; margin-bottom: 20px; }}
    .btn {{ display: inline-block; background-color: #059669; color: #ffffff !important; padding: 10px 20px; border-radius: 6px; text-decoration: none; font-weight: 600; margin: 16px 0; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h2 style="margin: 0; color: #065f46;">{html.escape(organization_name)} — Purchase Order</h2>
    </div>
    <p>Dear {html.escape(supplier_name)} Team,</p>
    <p>We are pleased to issue Purchase Order <strong>#{html.escape(po_number)}</strong> for your accepted quotation.</p>
    
    <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; padding: 16px; border-radius: 6px; margin: 16px 0;">
      <p style="margin: 4px 0;"><strong>PO Number:</strong> #{html.escape(po_number)}</p>
      <p style="margin: 4px 0;"><strong>Total Value:</strong> {html.escape(total_amount)} {html.escape(currency)}</p>
      <p style="margin: 4px 0;"><strong>Reference ID:</strong> <code>{po_id}</code></p>
    </div>

    <p>Please acknowledge receipt and confirm expected delivery milestones.</p>
    
    <div style="text-align: center;">
      <a href="{po_link}" class="btn">View Purchase Order</a>
    </div>
  </div>
</body>
</html>"""

    return subject, text_body, html_body
