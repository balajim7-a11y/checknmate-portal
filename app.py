import json
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
    """Smart sender: Tries custom message first, falls back to guaranteed template if session is closed."""
    
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

    # 2. Build Custom Message Content
    if message_type == "upcoming":
        custom_body = (
            f"Hi from Check N Mate! ♟️\n\n"
            f"This is an automated reminder that the fee of ₹{amount} for {student_name} is due in 3 days.\n\n"
            f"Pay securely here: {short_url}\n\n"
            f"Thank you!"
        )
    else:
        custom_body = (
            f"URGENT: Hi from Check N Mate! ♟️\n\n"
            f"The fee of ₹{amount} for {student_name} is currently OVERDUE.\n\n"
            f"Please complete your payment immediately using this secure link: {short_url}\n\n"
            f"Thank you!"
        )

    try:
        # 3. Attempt Custom Free-Form Message (Requires open 24hr window)
        message = twilio_client.messages.create(
            body=custom_body,
            from_=st.secrets["twilio"]["sandbox_number"],
            to=f"whatsapp:{parent_phone}",
        )
        return short_url, message.sid, "Custom Text"
        
    except Exception as e:
        # 4. Fallback to Guaranteed Twilio Template if 24hr window is closed
        if "ContentSid Required" in str(e) or "400" in str(e):
            status_label = f"{student_name} [FEE {message_type.upper()}]"
            message = twilio_client.messages.create(
                content_sid="HXfe5ab5f00277942d4d4200328b4d403c", 
                content_variables=json.dumps({
                    "1": status_label, 
                    "2": short_url
                }),
                from_=st.secrets["twilio"]["sandbox_number"],
                to=f"whatsapp:{parent_phone}",
            )
            return short_url, message.sid, "Template Fallback"
        else:
            # If it's a completely different error (like wrong phone number), raise it
            raise e

# --- DASHBOARD UI & TABS ---
tab1, tab2, tab3 = st.tabs(["📊 Global Roster", "⚙️ Run Daily Batch Automations", "📲 Single Demo Trigger"])

# TAB 1: Database View
with tab1:
    st.header("Active Student Roster")
    st.write("Live synchronization with PostgreSQL backend.")
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        
    try:
        df = conn.query("SELECT * FROM Students ORDER BY due_date ASC;", ttl="0m")
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning("Ensure your 'Students' table is finalized in Neon.")

# TAB 2: Batch Processing Engine
with tab2:
    st.header("Automated Workflow Engine")
    st.write("In production, a Cloud Scheduler runs this script daily. For the demo, trigger the batch manually below.")
    
    if st.button("🚀 Execute Daily Notification Batch"):
        with st.spinner("Querying database and processing queues..."):
            try:
                # Fetch fresh data
                df = conn.query("SELECT * FROM Students WHERE payment_status = 'Pending';", ttl="0m")
                df['due_date'] = pd.to_datetime(df['due_date']).dt.date
                today = datetime.now().date()
                three_days_from_now = today + timedelta(days=3)

                upcoming_students = df[df['due_date'] == three_days_from_now]
                overdue_students = df[df['due_date'] < today]

                st.markdown("### Execution Report")
                
                # Process 3-Day Reminders
                if not upcoming_students.empty:
                    st.write(f"**Processing {len(upcoming_students)} Upcoming Reminders:**")
                    for index, row in upcoming_students.iterrows():
                        try:
                            link, sid, msg_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "upcoming")
                            st.success(f"✅ Sent to {row['student_name']} (via {msg_type}) - Link: {link}")
                        except Exception as e:
                            st.error(f"❌ Failed to send to {row['student_name']}: {e}")
                else:
                    st.info("No fees due exactly 3 days from now.")

                # Process Overdue Reminders
                if not overdue_students.empty:
                    st.write(f"**Processing {len(overdue_students)} Overdue Notices:**")
                    for index, row in overdue_students.iterrows():
                        try:
                            link, sid, msg_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "overdue")
                            st.warning(f"⚠️ Sent to {row['student_name']} (via {msg_type}) - Link: {link}")
                        except Exception as e:
                            st.error(f"❌ Failed to send to {row['student_name']}: {e}")
                else:
                    st.info("No overdue payments detected.")

            except Exception as e:
                st.error(f"Database operation failed: {e}")

# TAB 3: Single Test Trigger
with tab3:
    st.header("Interactive Demo Trigger")
    st.write("Use this to fire a custom test message to any number right now.")
    with st.form("demo_form"):
        col1, col2 = st.columns(2)
        with col1:
            demo_name = st.text_input("Student Name", value="Demo User")
            demo_amount = st.number_input("Fee Amount (₹)", value=1500, step=100)
            demo_type = st.selectbox("Message Context", ["upcoming", "overdue"])
        with col2:
            demo_phone = st.text_input("Parent Phone (E.164 Format)", value="+919019011331")
            
        submit_btn = st.form_submit_button("Fire Test Payload")

        if submit_btn:
            with st.spinner("Generating Link & Dispatching WhatsApp..."):
                try:
                    link, sid, msg_type = dispatch_whatsapp_payload(
                        student_name=demo_name,
                        parent_phone=demo_phone,
                        amount=demo_amount,
                        message_type=demo_type
                    )
                    st.success(f"✅ Message delivered via {msg_type}!")
                    st.info(f"**Razorpay Short URL Generated:** {link}")
                except Exception as e:
                    st.error(f"Failed to execute workflow: {e}")
