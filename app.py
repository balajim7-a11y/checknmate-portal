import pandas as pd
import razorpay
import streamlit as st
from twilio.rest import Client
from datetime import datetime, timedelta

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Check N Mate Admin", page_icon="♟️", layout="wide")
st.title("♟️ Check N Mate - Admin Dashboard")

# --- DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    return st.connection("postgresql", type="sql")

conn = init_connection()

# --- NOTIFICATION & PAYMENT LOGIC ---
def dispatch_whatsapp_payload(student_name: str, parent_phone: str, amount: int, message_type: str):
    """Generates a Razorpay link and sends a contextual WhatsApp message."""
    
    rzp_client = razorpay.Client(auth=(st.secrets["razorpay"]["key_id"], st.secrets["razorpay"]["key_secret"]))
    twilio_client = Client(st.secrets["twilio"]["account_sid"], st.secrets["twilio"]["auth_token"])

    # 1. Generate Razorpay Link
    payment_link = rzp_client.payment_link.create({
        "amount": int(amount * 100),  
        "currency": "INR",
        "description": f"Fee payment for {student_name}",
        "customer": {"name": student_name, "contact": parent_phone},
        "notify": {"sms": False, "email": False},
    })
    short_url = payment_link["short_url"]

    # 2. Determine Message Context
    if message_type == "upcoming":
        body = (
            f"Hi from Check N Mate! ♟️\n\n"
            f"This is an automated reminder that the fee of ₹{amount} for {student_name} is due in 3 days.\n\n"
            f"Pay securely here: {short_url}\n\n"
            f"Thank you!"
        )
    elif message_type == "overdue":
        body = (
            f"URGENT: Hi from Check N Mate! ♟️\n\n"
            f"The fee of ₹{amount} for {student_name} is currently OVERDUE.\n\n"
            f"Please complete your payment immediately using this secure link: {short_url}\n\n"
            f"Thank you!"
        )

    # 3. Dispatch via Twilio (Requires active 24hr session window in Sandbox)
    message = twilio_client.messages.create(
        body=body,
        from_=st.secrets["twilio"]["sandbox_number"],
        to=f"whatsapp:{parent_phone}",
    )
    
    return short_url, message.sid


# --- DASHBOARD UI & TABS ---
tab1, tab2 = st.tabs(["📊 Global Roster", "⚙️ Run Daily Batch Automations"])

# TAB 1: Database View
with tab1:
    st.header("Active Student Roster")
    st.write("Live synchronization with PostgreSQL backend.")
    try:
        df = conn.query("SELECT * FROM Students;", ttl="0m") # 0m forces fresh data
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning("Ensure your 'Students' table is finalized in Neon with columns: student_name, parent_phone, fee_amount, due_date, payment_status.")

# TAB 2: Batch Processing Engine
with tab2:
    st.header("Automated Workflow Engine")
    st.write("In production, a Cloud Scheduler runs this script daily. For the demo, trigger the batch manually below.")
    
    if st.button("🚀 Execute Daily Notification Batch"):
        with st.spinner("Querying database and processing queues..."):
            try:
                # Fetch fresh data
                df = conn.query("SELECT * FROM Students WHERE payment_status = 'Pending';", ttl="0m")
                
                # Convert due_date string/db-date to Pandas datetime for math
                df['due_date'] = pd.to_datetime(df['due_date']).dt.date
                today = datetime.now().date()
                three_days_from_now = today + timedelta(days=3)

                # Isolate the target records
                upcoming_students = df[df['due_date'] == three_days_from_now]
                overdue_students = df[df['due_date'] < today]

                st.markdown("### Execution Report")
                
                # Process 3-Day Reminders
                if not upcoming_students.empty:
                    st.write(f"**Processing {len(upcoming_students)} Upcoming Reminders:**")
                    for index, row in upcoming_students.iterrows():
                        try:
                            link, sid = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "upcoming")
                            st.success(f"✅ Upcoming Reminder sent to {row['student_name']} ({row['parent_phone']}) - Link: {link}")
                        except Exception as e:
                            st.error(f"❌ Failed to send to {row['student_name']}: {e}")
                else:
                    st.info("No fees due exactly 3 days from now.")

                # Process Overdue Reminders
                if not overdue_students.empty:
                    st.write(f"**Processing {len(overdue_students)} Overdue Notices:**")
                    for index, row in overdue_students.iterrows():
                        try:
                            link, sid = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "overdue")
                            st.warning(f"⚠️ Overdue Notice sent to {row['student_name']} ({row['parent_phone']}) - Link: {link}")
                        except Exception as e:
                            st.error(f"❌ Failed to send to {row['student_name']}: {e}")
                else:
                    st.info("No overdue payments detected.")

            except Exception as e:
                st.error(f"Database operation failed: {e}")
