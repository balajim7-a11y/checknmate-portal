from fastapi import FastAPI, Request, Header, HTTPException
import hmac
import hashlib
import json
import datetime
import os
import uuid
from sqlalchemy import create_engine, text

# --- Configuration ---
# Set these in your Google Cloud Run environment variables
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "your_fallback_secret") 
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@your-neon-hostname.neon.tech/dbname")

app = FastAPI()
engine = create_engine(DATABASE_URL)

def verify_razorpay_signature(raw_body: bytes, signature: str) -> bool:
    expected_signature = hmac.new(
        key=RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)

@app.post("/webhook/razorpay")
async def razorpay_webhook(request: Request, x_razorpay_signature: str = Header(None)):
    raw_body = await request.body()
    if not x_razorpay_signature or not verify_razorpay_signature(raw_body, x_razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid Signature")

    payload = json.loads(raw_body.decode('utf-8'))
    
    if payload.get("event") == "payment.captured":
        entity = payload["payload"]["payment"]["entity"]
        
        gateway_ref = entity.get("id")
        amount_paid = entity.get("amount") / 100 
        payment_mode = entity.get("method")
        parent_phone = entity.get("contact") 
        
        if parent_phone and parent_phone.startswith("+91"):
            parent_phone = parent_phone[3:]

        payment_date = datetime.date.today()
        
        try:
            with engine.begin() as conn: 
                result = conn.execute(
                    text("SELECT student_id FROM Students WHERE parent_phone = :phone AND status = 'Active' LIMIT 1;"),
                    {"phone": parent_phone}
                ).fetchone()

                new_txn_id = f"txn_{uuid.uuid4().hex[:12]}"

                if result:
                    student_id = result[0]
                    next_due = payment_date + datetime.timedelta(days=30)
                    
                    conn.execute(
                        text("""
                            INSERT INTO Fee_Transactions (transaction_id, student_id, amount_paid, payment_mode, payment_date, transaction_status, gateway_reference, logged_by)
                            VALUES (:t_id, :s_id, :amt, :mode, :p_date, 'Success', :ref, 'usr_admin_001');
                        """),
                        {"t_id": new_txn_id, "s_id": student_id, "amt": amount_paid, "mode": payment_mode, "p_date": payment_date, "ref": gateway_ref}
                    )
                    
                    conn.execute(
                        text("""
                            UPDATE Student_Batches 
                            SET next_due_date = :next_due
                            WHERE student_id = :s_id;
                        """),
                        {"next_due": next_due, "s_id": student_id}
                    )
                    
                    conn.execute(
                        text("""
                            UPDATE Students 
                            SET account_fee_status = 'Paid' 
                            WHERE student_id = :s_id;
                        """),
                        {"s_id": student_id}
                    )
                    
                else:
                    # Unmatched / Orphan record logic
                    conn.execute(
                        text("""
                            INSERT INTO Fee_Transactions (transaction_id, student_id, amount_paid, payment_mode, payment_date, transaction_status, gateway_reference, logged_by)
                            VALUES (:t_id, NULL, :amt, :mode, :p_date, 'Unmatched', :ref, 'usr_admin_001');
                        """),
                        {"t_id": new_txn_id, "amt": amount_paid, "mode": payment_mode, "p_date": payment_date, "ref": gateway_ref}
                    )
                    
            return {"status": "success", "message": "Webhook processed"}
            
        except Exception as e:
            print(f"Database Error: {e}")
            return {"status": "error", "message": "Internal processing error"}
            
    return {"status": "ignored", "message": "Not a captured event"}
