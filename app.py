import json
import pandas as pd
import razorpay
import streamlit as st
from twilio.rest import Client

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Check N Mate Admin", page_icon="♟️", layout="wide")
st.title("♟️ Check N Mate - Admin Dashboard")

# --- DATABASE CONNECTION ---
# Establish connection to Neon PostgreSQL securely using Streamlit Secrets
@st.cache_resource
def init_connection():
    return st.connection("postgresql", type="sql")

conn = init_connection()


# --- NOTIFICATION & PAYMENT LOGIC ---
def trigger_whatsapp_reminder(student_name: str, parent_phone: str, amount: int):
    """Generates a dynamic Razorpay link and dispatches it via Twilio WhatsApp."""
    
    # Initialize API Clients
    rzp_client = razorpay.Client(
        auth=(
            st.secrets["razorpay"]["key_id"],
            st.secrets["razorpay"]["key_secret"],
        )
    )

    twilio_client = Client(
        st.secrets["twilio"]["account_sid"],
        st.secrets["twilio"]["auth_token"],
    )

    # 1. Create Dynamic Razorpay Payment Link
    payment_link = rzp_client.payment_link.create(
        {
            "amount": int(amount * 100),  # Convert to paise for Razorpay API
            "currency": "INR",
            "description": f"Fee payment for {student_name}",
            "customer": {"name": student_name, "contact": parent_phone},
            "notify": {"sms": False, "email": False},
        }
    )
    short_url = payment_link["short_url"]

    # 2. Dispatch WhatsApp message using Twilio's approved Sandbox Template
    # We must use content_sid and content_variables for Twilio trial accounts
    message = twilio_client.messages.create(
        content_sid="HXfe5ab5f00277942d4d4200328b4d403c", # Template ID from your Twilio console
        content_variables=json.dumps({
            "1": student_name, 
            "2": short_url
        }),
        from_=st.secrets["twilio"]["sandbox_number"],
        to=f"whatsapp:{parent_phone}",
    )
    
    return short_url, message.sid


# --- DASHBOARD UI & TABS ---
tab1, tab2 = st.tabs(["📊 Global Roster", "📲 Event-Driven Automations (Demo)"])

# TAB 1: Database View
with tab1:
    st.header("Active Student Roster")
    st.write("Live synchronization with PostgreSQL backend.")
    
    try:
        # Pulling existing data from your configured Neon table
        df = conn.query("SELECT * FROM Students;", ttl="10m")
        st.dataframe(df, use_container_width=True)
    except Exception as e:
        st.warning("Awaiting schema setup. Ensure your 'Students' table is finalized in Neon.")
        st.caption(f"Database Error details: {e}")

# TAB 2: Stakeholder Presentation Demo View
with tab2:
    st.header("Automated Workflow Demonstration")
    st.write("Simulate the backend scheduled cron job for upcoming due dates.")
    
    st.markdown("### Trigger '3-Day Prior' Notification")
    
    with st.form("demo_form"):
        col1, col2 = st.columns(2)
        with col1:
            demo_name = st.text_input("Student Name", value="Demo Student")
            demo_amount = st.number_input("Fee Amount (₹)", value=1500, step=100)
        with col2:
            # Using your successfully registered sandbox number for the live test
            demo_phone = st.text_input("Parent Phone (E.164 Format)", value="+919019011331")
            
        submit_btn = st.form_submit_button("Run Automation Workflow")

        if submit_btn:
            with st.spinner("Generating API link and dispatching WhatsApp payload..."):
                try:
                    link, sid = trigger_whatsapp_reminder(
                        student_name=demo_name,
                        parent_phone=demo_phone,
                        amount=demo_amount,
                    )
                    st.success("✅ Event triggered successfully! Check your phone.")
                    st.info(f"**Razorpay Short URL Generated:** {link}")
                    st.caption(f"Twilio Message SID: {sid}")
                except Exception as e:
                    st.error(f"Failed to execute workflow: {e}")
