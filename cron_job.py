import os
import time
from datetime import datetime
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

    today = datetime.now().date()
    current_day = today.day

    # Trigger strictly on the 2nd or the 5th of the month
    if current_day == 2:
        notice_type = "Monthly Advance Reminder (Due on 5th)"
    elif current_day == 5:
        notice_type = "Final Deadline Notice (Due Today - Last Day)"
    else:
        print(f"Today is day {current_day} of the month. No automated fee notification scheduled for today.")
        return

    with engine.connect() as connection:
        # Fetches ONLY unpaid (Pending) records. If paid between 2nd and 5th, they are automatically excluded.
        result = connection.execute(text("""
            SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name 
            FROM Students 
            WHERE payment_status = 'Pending';
        """))
        students = result.fetchall()

        if not students:
            print("No pending payments found. All fees cleared!")
            return

        print(f"Running fee notification batch for date: {today} ({notice_type})...")

        for row in students:
            student_id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name = row
            
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
                print(f"[{notice_type}] Generated link for {student_name} at {franchise_name}: {short_url}")
            except Exception as err:
                print(f"[{notice_type}] Failed to generate link for {student_name}: {err}")

if __name__ == "__main__":
    run_automated_batch()
