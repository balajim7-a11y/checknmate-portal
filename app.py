import json
import time
from datetime import datetime, timedelta
import pandas as pd
import razorpay
import bcrypt
from sqlalchemy import text
import streamlit as st

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Check N Mate - Fee Portal", page_icon="♟️", layout="wide")

# --- 2. DATABASE CONNECTION & BULLETPROOF USER SYNC ---
@st.cache_resource
def init_connection():
    return st.connection("postgresql", type="sql")

conn = init_connection()

def ensure_users_table():
    with conn.session as session:
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS Users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL,
                franchise_name VARCHAR(100) DEFAULT 'Company HQ'
            );
        """))
        session.commit()
        
        # Explicit Python-side check & upsert to avoid constraint mismatch errors
        default_users = [
            ("superadmin", "Admin123!", "Admin", "Company HQ"),
            ("company", "Company123!", "Company", "Company HQ"),
            ("franchise", "Franchise123!", "Franchise", "Whitefield Center")
        ]
        
        for uname, pwd, role, franchise in default_users:
            pwd_hash = bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            existing = session.execute(
                text("SELECT id FROM Users WHERE username = :u"), {"u": uname}
            ).fetchone()
            
            if existing:
                session.execute(
                    text("UPDATE Users SET password_hash = :h, role = :r, franchise_name = :f WHERE username = :u"),
                    {"h": pwd_hash, "r": role, "f": franchise, "u": uname}
                )
            else:
                session.execute(
                    text("INSERT INTO Users (username, password_hash, role, franchise_name) VALUES (:u, :h, :r, :f)"),
                    {"u": uname, "h": pwd_hash, "r": role, "f": franchise}
                )
        session.commit()

ensure_users_table()

# --- DEMO FRANCHISE LIST ---
FRANCHISE_OPTIONS = ["Company HQ", "Whitefield Center", "Attibele Center", "Mysore Center"]

# --- 3. DATABASE-BACKED AUTHENTICATION ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""
    st.session_state["franchise_name"] = ""

def login_screen():
    _, col_center, _ = st.columns([1.2, 2, 1.2])
    with col_center:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<h1 style='text-align: center;'>♟️ Check N Mate</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #666;'>Secure Fee Management & Operations Portal</p><br>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            st.markdown("### 🔒 Database Authentication")
            username_input = st.text_input("Username")
            password_input = st.text_input("Password", type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            submit_login = st.form_submit_button("Sign In", use_container_width=True)
            
            if submit_login:
                try:
                    df_user = conn.query(
                        "SELECT username, password_hash, role, franchise_name FROM Users WHERE username = :uname;",
                        params={"uname": username_input.lower()},
                        ttl="0m"
                    )
                    
                    if not df_user.empty:
                        stored_hash = df_user.iloc[0]["password_hash"]
                        if bcrypt.checkpw(password_input.encode('utf-8'), stored_hash.encode('utf-8')):
                            st.session_state["logged_in"] = True
                            st.session_state["username"] = df_user.iloc[0]["username"]
                            st.session_state["role"] = df_user.iloc[0]["role"]
                            st.session_state["franchise_name"] = df_user.iloc[0]["franchise_name"]
                            st.rerun()
                        else:
                            st.error("😕 Invalid username or password.")
                    else:
                        st.error("😕 Invalid username or password.")
                except Exception as e:
                    st.error(f"Authentication error: {e}")

if not st.session_state["logged_in"]:
    login_screen()
    st.stop() 

# --- SIDEBAR: USER INFO & LOGOUT ---
with st.sidebar:
    st.markdown("### 👤 User Session")
    st.info(f"**User:** {st.session_state['username'].capitalize()}\n\n**Role:** {st.session_state['role']}\n\n**Center:** {st.session_state['franchise_name']}")
    if st.button("🚪 Logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.session_state["franchise_name"] = ""
        st.rerun()

# --- 4. PAYMENT & MESSAGING ENGINE (Simulator) ---
def dispatch_whatsapp_payload(student_name: str, parent_phone: str, amount: float, message_type: str):
    raw_phone = ''.join(filter(str.isdigit, str(parent_phone)))
    clean_phone = f"+91{raw_phone}" if len(raw_phone) == 10 else f"+{raw_phone}"

    rzp_client = razorpay.Client(auth=(st.secrets["razorpay"]["key_id"], st.secrets["razorpay"]["key_secret"]))
    expiry_timestamp = int(time.time()) + (3 * 24 * 60 * 60)

    try:
        payment_link = rzp_client.payment_link.create({
            "amount": int(amount * 100),
            "currency": "INR",
            "expire_by": expiry_timestamp,
            "description": f"Fee payment for {student_name}",
            "customer": {"name": student_name, "contact": clean_phone}
        })
        short_url = payment_link["short_url"]
    except Exception as rzp_error:
        raise Exception(f"[Razorpay Error] {rzp_error}")

    simulated_sid = f"SM{int(time.time())}DEMO"
    return short_url, simulated_sid, "Simulated WhatsApp Live Link"

# --- 5. UI DASHBOARD & SCOPED QUERIES ---
st.title("♟️ Check N Mate - Admin Portal")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Active Roster", 
    "⚙️ Run Automations", 
    "🗓️ Manage Due Dates", 
    "🧑‍🎓 Student Management"
])

def get_scoped_students_query():
    if st.session_state["role"] in ["Admin", "Company"]:
        return "SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name, last_updated_by FROM Students ORDER BY due_date ASC;"
    else:
        return f"SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name, last_updated_by FROM Students WHERE franchise_name = '{st.session_state['franchise_name']}' ORDER BY due_date ASC;"

# --- TAB 1: ACTIVE ROSTER ---
with tab1:
    st.header("Student Fee Roster")
    col_a, _ = st.columns([1, 5])
    with col_a:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
        
    try:
        query = get_scoped_students_query()
        df = conn.query(query, ttl="0m")
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Database Error: {e}")

# --- TAB 2: BATCH AUTOMATIONS ---
with tab2:
    st.header("Automated Messaging Engine")
    if st.button("🚀 Execute Daily Notification Batch", type="primary"):
        with st.spinner("Processing pending payments..."):
            try:
                base_q = get_scoped_students_query().replace("ORDER BY due_date ASC;", "AND payment_status = 'Pending' ORDER BY due_date ASC;")
                df = conn.query(base_q, ttl="0m")
                if df.empty:
                    st.info("No pending payments found.")
                else:
                    df['due_date'] = pd.to_datetime(df['due_date']).dt.date
                    today = datetime.now().date()
                    
                    upcoming_students = df[df['due_date'] == today + timedelta(days=3)]
                    overdue_students = df[df['due_date'] < today]

                    if not upcoming_students.empty:
                        st.subheader(f"Upcoming Reminders ({len(upcoming_students)})")
                        for _, row in upcoming_students.iterrows():
                            try:
                                link, sid, delivery_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "upcoming")
                                st.success(f"✅ Sent to **{row['student_name']}** via {delivery_type} | [Payment Link]({link})")
                            except Exception as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                            
                    if not overdue_students.empty:
                        st.subheader(f"Overdue Notices ({len(overdue_students)})")
                        for _, row in overdue_students.iterrows():
                            try:
                                link, sid, delivery_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "overdue")
                                st.warning(f"⚠️ Sent to **{row['student_name']}** via {delivery_type} | [Payment Link]({link})")
                            except Exception as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
            except Exception as e:
                st.error(f"Database batch operation failed: {e}")

# --- TAB 3: MANAGE DUE DATES ---
with tab3:
    st.header("🗓️ Manage Due Dates")
    st.caption("Update individual deadlines or use bulk update across records.")
    
    col_single, col_bulk = st.columns(2)
    
    with col_single:
        st.subheader("👤 Individual Update")
        try:
            df_students = conn.query(get_scoped_students_query(), ttl="0m")
            if not df_students.empty:
                with st.form("single_update_form"):
                    student_map = dict(zip(df_students['student_name'], df_students['id']))
                    selected_student = st.selectbox("Select Student", list(student_map.keys()))
                    
                    curr_date = df_students[df_students['student_name'] == selected_student]['due_date'].iloc[0]
                    st.write(f"Current due date: **{curr_date}**")
                    
                    new_due_date = st.date_input("New Due Date", key="single_date_input")
                    submit_single = st.form_submit_button("Update Student")
                    
                    if submit_single:
                        student_id = int(student_map[selected_student])
                        with conn.session as session:
                            session.execute(
                                text("UPDATE Students SET due_date = :due_date, last_updated_by = :user WHERE id = :id"),
                                {"due_date": new_due_date, "user": st.session_state["username"], "id": student_id}
                            )
                            session.commit()
                        st.success(f"Updated {selected_student}'s due date to {new_due_date}!")
                        st.cache_data.clear()
            else:
                st.warning("No records found.")
        except Exception as e:
            st.error(f"Error loading student list: {e}")

    with col_bulk:
        st.subheader("⚡ Bulk Update")
        with st.form("bulk_update_form"):
            bulk_date = st.date_input("Set Date for Records", key="bulk_date_input")
            submit_bulk = st.form_submit_button("Apply Update")
            
            if submit_bulk:
                try:
                    with conn.session as session:
                        if st.session_state["role"] in ["Admin", "Company"]:
                            session.execute(
                                text("UPDATE Students SET due_date = :bulk_date, last_updated_by = :user"),
                                {"bulk_date": bulk_date, "user": st.session_state["username"]}
                            )
                        else:
                            session.execute(
                                text("UPDATE Students SET due_date = :bulk_date, last_updated_by = :user WHERE franchise_name = :franchise"),
                                {"bulk_date": bulk_date, "user": st.session_state["username"], "franchise": st.session_state["franchise_name"]}
                            )
                        session.commit()
                    st.success(f"Successfully updated records to {bulk_date}!")
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Bulk update failed: {e}")

# --- TAB 4: STUDENT MANAGEMENT ---
with tab4:
    st.header("🧑‍🎓 Student Directory & Operations")
    
    st.subheader("Current Database View")
    try:
        df_students = conn.query(get_scoped_students_query(), ttl="0m")
        if not df_students.empty:
            st.dataframe(df_students, use_container_width=True, hide_index=True)
        else:
            st.info("No students found.")
    except Exception as e:
        st.error(f"Error loading students: {e}")
        df_students = pd.DataFrame() 

    st.divider()
    st.subheader("Administrative Actions")
    
    action_tabs = st.tabs(["➕ Enroll Student", "✏️ Update Profile", "❌ Remove Student"])

    with action_tabs[0]:
        with st.form("add_student_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            franchise_choices = [st.session_state["franchise_name"]] if st.session_state["role"] == "Franchise" else FRANCHISE_OPTIONS

            with c1:
                new_name = st.text_input("Student Name")
                new_phone = st.text_input("Parent Phone (10 digits)")
            with c2:
                new_amount = st.number_input("Fee (₹)", min_value=100.0, value=1200.0)
                new_due_date = st.date_input("First Due Date")
            with c3:
                new_status = st.selectbox("Status", ["Pending", "Paid"])
                new_franchise = st.selectbox("Assign to Franchise", franchise_choices)
                
            if st.form_submit_button("Add to Database"):
                if not new_name or not new_phone:
                    st.error("Name and Phone are required.")
                else:
                    try:
                        with conn.session as session:
                            check_query = text("SELECT COUNT(*) FROM Students WHERE student_name = :name AND parent_phone = :phone")
                            duplicate_count = session.execute(check_query, {"name": new_name, "phone": new_phone}).scalar()
                            
                            if duplicate_count > 0:
                                st.error(f"⚠️ A student named **{new_name}** with the phone number **{new_phone}** is already enrolled!")
                            else:
                                session.execute(
                                    text("INSERT INTO Students (student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name, last_updated_by) VALUES (:name, :phone, :amt, :date, :status, :franchise, :user)"),
                                    {"name": new_name, "phone": new_phone, "amt": new_amount, "date": new_due_date, "status": new_status, "franchise": new_franchise, "user": st.session_state["username"]}
                                )
                                session.commit()
                                st.success(f"Successfully added {new_name} to {new_franchise}!")
                                st.cache_data.clear()
                                
                    except Exception as e:
                        st.error(f"Error adding student: {e}")

    with action_tabs[1]:
        if not df_students.empty:
            student_map = dict(zip(df_students['student_name'], df_students['id']))
            selected = st.selectbox("Select Student to Update", list(student_map.keys()))
            
            curr_data = df_students[df_students['student_name'] == selected].iloc[0]
            curr_franchise = curr_data.get('franchise_name', 'Company HQ')
            franchise_choices = FRANCHISE_OPTIONS if st.session_state["role"] in ["Admin", "Company"] else [st.session_state["franchise_name"]]
            franchise_idx = franchise_choices.index(curr_franchise) if curr_franchise in franchise_choices else 0
            
            with st.form("update_student_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    upd_phone = st.text_input("Phone", value=curr_data['parent_phone'])
                    upd_amount = st.number_input("Fee (₹)", value=float(curr_data['fee_amount']))
                with c2:
                    upd_date = st.date_input("Due Date", value=pd.to_datetime(curr_data['due_date']))
                    upd_status = st.selectbox("Status", ["Pending", "Paid"], index=0 if curr_data['payment_status'] == "Pending" else 1)
                with c3:
                    upd_franchise = st.selectbox("Franchise", franchise_choices, index=franchise_idx)
                
                if st.form_submit_button("Save Changes"):
                    try:
                        with conn.session as session:
                            session.execute(
                                text("UPDATE Students SET parent_phone=:phone, fee_amount=:amt, due_date=:date, payment_status=:status, franchise_name=:franchise, last_updated_by=:user WHERE id=:id"),
                                {"phone": upd_phone, "amt": upd_amount, "date": upd_date, "status": upd_status, "franchise": upd_franchise, "user": st.session_state["username"], "id": int(student_map[selected])}
                            )
                            session.commit()
                        st.success(f"Updated {selected}'s profile!")
                        st.cache_data.clear()
                    except Exception as e:
                        st.error(f"Error updating student: {e}")
        else:
            st.info("No records available to update.")

    with action_tabs[2]:
        if st.session_state["role"] == "Franchise":
            st.error("🚫 Access Denied: Franchise users cannot permanently delete records.")
        else:
            if not df_students.empty:
                student_map = dict(zip(df_students['student_name'], df_students['id']))
                del_selected = st.selectbox("Select Student to Permanently Delete", list(student_map.keys()))
                
                st.warning(f"You are about to permanently remove **{del_selected}**.")
                confirm_delete = st.checkbox("I confirm that I want to delete this record.")
                
                if st.button("⚠️ Permanently Delete Record", type="primary", disabled=not confirm_delete):
                    try:
                        with conn.session as session:
                            session.execute(text("DELETE FROM Students WHERE id=:id"), {"id": int(student_map[del_selected])})
                            session.commit()
                        st.success(f"Deleted {del_selected} from the database.")
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error deleting student: {e}")
            else:
                st.info("No records available to delete.")
