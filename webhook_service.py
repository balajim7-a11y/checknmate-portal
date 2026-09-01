import datetime
import hashlib
import hmac
import json
import logging
import os
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "your_fallback_secret")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://user:password@your-neon-hostname.neon.tech/dbname",
)

app = FastAPI()
engine = create_engine(DATABASE_URL)


def verify_razorpay_signature(raw_body: bytes, signature: str) -> bool:
    expected_signature = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


def _extract_payment_entity(payload: dict) -> dict:
    try:
        return payload["payload"]["payment"]["entity"]
    except (KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="Malformed webhook payload") from exc


@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(None)):
    try:
        raw_body = await request.body()
    except Exception as exc:
        logger.exception("Failed to read Razorpay webhook request body")
        raise HTTPException(status_code=400, detail="Unable to read request body") from exc

    if not x_razorpay_signature or not verify_razorpay_signature(raw_body, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid Signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning("Invalid JSON in Razorpay webhook: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    if payload.get("event") != "payment.captured":
        return {"status": "ignored", "message": "Not a captured event"}

    entity = _extract_payment_entity(payload)

    try:
        gateway_ref = entity["id"]
        amount_paid = entity["amount"] / 100
        payment_mode = entity.get("method")
        parent_phone = entity.get("contact")
    except (KeyError, TypeError) as exc:
        logger.warning("Missing payment fields in Razorpay webhook payload")
        raise HTTPException(status_code=400, detail="Incomplete payment payload") from exc

    if parent_phone and parent_phone.startswith("+91"):
        parent_phone = parent_phone[3:]

    payment_date = datetime.date.today()

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT student_id FROM Students WHERE parent_phone = :phone AND status = 'Active' LIMIT 1;"
                ),
                {"phone": parent_phone},
            ).fetchone()

            new_txn_id = f"txn_{uuid.uuid4().hex[:12]}"

            if result:
                student_id = result[0]
                next_due = payment_date + datetime.timedelta(days=30)

                conn.execute(
                    text(
                        """
                            INSERT INTO Fee_Transactions (transaction_id, student_id, amount_paid, payment_mode, payment_date, transaction_status, gateway_reference, logged_by)
                            VALUES (:t_id, :s_id, :amt, :mode, :p_date, 'Success', :ref, 'usr_admin_001');
                        """
                    ),
                    {
                        "t_id": new_txn_id,
                        "s_id": student_id,
                        "amt": amount_paid,
                        "mode": payment_mode,
                        "p_date": payment_date,
                        "ref": gateway_ref,
                    },
                )

                conn.execute(
                    text(
                        """
                            UPDATE Student_Batches
                            SET next_due_date = :next_due
                            WHERE student_id = :s_id;
                        """
                    ),
                    {"next_due": next_due, "s_id": student_id},
                )

                conn.execute(
                    text(
                        """
                            UPDATE Students
                            SET account_fee_status = 'Paid'
                            WHERE student_id = :s_id;
                        """
                    ),
                    {"s_id": student_id},
                )
            else:
                conn.execute(
                    text(
                        """
                            INSERT INTO Fee_Transactions (transaction_id, student_id, amount_paid, payment_mode, payment_date, transaction_status, gateway_reference, logged_by)
                            VALUES (:t_id, NULL, :amt, :mode, :p_date, 'Unmatched', :ref, 'usr_admin_001');
                        """
                    ),
                    {
                        "t_id": new_txn_id,
                        "amt": amount_paid,
                        "mode": payment_mode,
                        "p_date": payment_date,
                        "ref": gateway_ref,
                    },
                )

        return {"status": "success", "message": "Webhook processed"}

    except SQLAlchemyError as exc:
        logger.exception("Database error processing Razorpay webhook")
        raise HTTPException(status_code=500, detail="Internal processing error") from exc
    except Exception as exc:
        logger.exception("Unexpected error processing Razorpay webhook")
        raise HTTPException(status_code=500, detail="Internal processing error") from exc
