import os
import time
from datetime import datetime, timedelta
import razorpay
from sqlalchemy import create_engine, text

def run_automated_batch():
    db_url = os.environ.get("DATABASE_URL")
    rzp_key_id = os.environ.get("RAZORPAY_KEY_ID")
    rzp_key_secret = os.environ.get("RAZORPAY_KEY_SECRET")

    if not db_url:
        raise ValueError("DATABASE_URL environment variable is missing.")

    engine = create_engine(db_url)
    rzp_client = razorpay.Client(auth=(rzp_key_id, rzp_key_secret))

    with engine.connect() as connection:
        result = connection.execute(text("""
            SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name 
            FROM Students 
            WHERE payment_status = 'Pending' 
            ORDER BY due_date ASC;
        """))
        students = result.fetchall()

        if not students:
            print("No pending payments found.")
            return

        today = datetime.now().date()
        print(f"Running automated notification batch for {today}...")

        for row in students:
            student_id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name = row
            
            # Normalize due_date to date object if stored as datetime/timestamp
            if hasattr(due_date, "date"):
                d_date = due_date.date()
            else:
                d_date = datetime.strptime(str(due_date), "%Y-%m-%d").date()

            if d_date == today + timedelta(days=3) or d_date < today:
                notice_type = "Upcoming Reminder" if d_date > today else "Overdue Notice"
                
                # Format phone number
                raw_phone = ''.join(filter(str.isdigit, str(parent_phone)))
                clean_phone = f"+91{raw_phone}" if len(raw_phone) == 10 else f"+{raw_phone}"

                try:
                    expiry_timestamp = int(time.time()) + (3 * 24 * 60 * 60)
                    payment_link = rzp_client.payment_link.create({
                        "amount": int(float(fee_amount) * 100),
                        "currency": "INR",
                        "expire_by": expiry_timestamp,
                        "description": f"Fee payment for {student_name}",
                        "customer": {"name": student_name, "contact": clean_phone}
                    })
                    short_url = payment_link["short_url"]
                    print(f"[{notice_type}] Successfully generated link for {student_name} ({franchise_name}): {short_url}")
                except Exception as err:
                    print(f"[{notice_type}] Failed to generate link for {student_name}: {err}")

if __name__ == "__main__":
    run_automated_batch()
