import json
import logging
import time
from datetime import datetime, timedelta

import pandas as pd
import razorpay
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
import streamlit as st

logger = logging.getLogger(__name__)

# --- 1. PAGE CONFIGURATION ---
st.set_page_config(page_title="Check N Mate - Fee Portal", page_icon="♟️", layout="wide")

# --- 2. AUTHENTICATION & ROLE MANAGEMENT ---
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    st.session_state["username"] = ""
    st.session_state["role"] = ""

def login_screen():
    st.title("🔒 Check N Mate - Secure Login")
    st.markdown("Please log in with your assigned Admin, Company, or Franchise credentials.")

    try:
        admin_password = st.secrets["admin_password"]
        company_password = st.secrets["company_password"]
        franchise_password = st.secrets["franchise_password"]
    except (KeyError, FileNotFoundError, AttributeError):
        st.error("Authentication secrets are not configured. Check `.streamlit/secrets.toml`.")
        return
    
    with st.form("login_form"):
        username_input = st.text_input("Username")
        password_input = st.text_input("Password", type="password")
        submit_login = st.form_submit_button("Login")
        
        if submit_login:
            if username_input.lower() == "superadmin" and password_input == admin_password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "superadmin"
                st.session_state["role"] = "Admin"
                st.rerun()
            elif username_input.lower() == "company" and password_input == company_password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "company"
                st.session_state["role"] = "Company"
                st.rerun()
            elif username_input.lower() == "franchise" and password_input == franchise_password:
                st.session_state["logged_in"] = True
                st.session_state["username"] = "franchise"
                st.session_state["role"] = "Franchise"
                st.rerun()
            else:
                st.error("😕 Invalid username or password.")

if not st.session_state["logged_in"]:
    login_screen()
    st.stop() 

# --- SIDEBAR: USER INFO & LOGOUT ---
with st.sidebar:
    st.markdown("### 👤 User Session")
    st.info(f"**User:** {st.session_state['username'].capitalize()}\n\n**Role:** {st.session_state['role']}")
    if st.button("🚪 Logout"):
        st.session_state["logged_in"] = False
        st.session_state["username"] = ""
        st.session_state["role"] = ""
        st.rerun()

# --- 3. DATABASE CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        return st.connection("postgresql", type="sql")
    except Exception as exc:
        logger.exception("Failed to initialize database connection")
        raise RuntimeError("Unable to connect to PostgreSQL. Verify database settings in secrets.") from exc

try:
    conn = init_connection()
except RuntimeError as exc:
    st.error(str(exc))
    st.stop()

# --- DEMO FRANCHISE LIST ---
FRANCHISE_OPTIONS = ["Company HQ", "Whitefield Center", "Attibele Center", "Mysore Center"]

# --- 4. PAYMENT & MESSAGING ENGINE (Demo-Proof Simulator) ---
def dispatch_whatsapp_payload(student_name: str, parent_phone: str, amount: float, message_type: str):
    if not student_name or not str(student_name).strip():
        raise ValueError("Student name is required.")
    if not parent_phone or not str(parent_phone).strip():
        raise ValueError("Parent phone number is required.")
    if amount <= 0:
        raise ValueError("Fee amount must be greater than zero.")

    raw_phone = "".join(filter(str.isdigit, str(parent_phone)))
    if len(raw_phone) not in (10, 12, 13):
        raise ValueError(f"Invalid parent phone number: {parent_phone}")

    clean_phone = f"+91{raw_phone}" if len(raw_phone) == 10 else f"+{raw_phone}"

    try:
        razorpay_key_id = st.secrets["razorpay"]["key_id"]
        razorpay_key_secret = st.secrets["razorpay"]["key_secret"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Razorpay credentials are not configured in secrets.") from exc

    rzp_client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
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
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Razorpay returned an unexpected response.") from exc
    except Exception as rzp_error:
        raise RuntimeError(f"Razorpay payment link creation failed: {rzp_error}") from rzp_error

    simulated_sid = f"SM{int(time.time())}DEMO"
    return short_url, simulated_sid, "Simulated WhatsApp Live Link"

# --- 5. UI DASHBOARD ---
st.title("♟️ Check N Mate - Admin Portal")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Active Roster", 
    "⚙️ Run Automations", 
    "🗓️ Manage Due Dates", 
    "🧑‍🎓 Student Management"
])

# --- TAB 1: ACTIVE ROSTER ---
with tab1:
    st.header("Student Fee Roster")
    col_a, _ = st.columns([1, 5])
    with col_a:
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.cache_data.clear()
        
    try:
        df = conn.query("SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name, last_updated_by FROM Students ORDER BY due_date ASC;", ttl="0m")
        st.dataframe(df, use_container_width=True, hide_index=True)
    except SQLAlchemyError as exc:
        logger.exception("Failed to load active roster")
        st.error(f"Database error while loading roster: {exc}")
    except Exception as exc:
        logger.exception("Unexpected error while loading active roster")
        st.error(f"Unable to load roster: {exc}")

# --- TAB 2: BATCH AUTOMATIONS ---
with tab2:
    st.header("Automated Messaging Engine")
    if st.button("🚀 Execute Daily Notification Batch", type="primary"):
        with st.spinner("Processing pending payments..."):
            try:
                df = conn.query("SELECT * FROM Students WHERE payment_status = 'Pending';", ttl="0m")
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
                            except (ValueError, RuntimeError) as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                            except Exception as err:
                                logger.exception("Failed to send upcoming reminder for %s", row["student_name"])
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                            
                    if not overdue_students.empty:
                        st.subheader(f"Overdue Notices ({len(overdue_students)})")
                        for _, row in overdue_students.iterrows():
                            try:
                                link, sid, delivery_type = dispatch_whatsapp_payload(row['student_name'], row['parent_phone'], row['fee_amount'], "overdue")
                                st.warning(f"⚠️ Sent to **{row['student_name']}** via {delivery_type} | [Payment Link]({link})")
                            except (ValueError, RuntimeError) as err:
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
                            except Exception as err:
                                logger.exception("Failed to send overdue notice for %s", row["student_name"])
                                st.error(f"❌ Failed for {row['student_name']}: {err}")
            except SQLAlchemyError as exc:
                logger.exception("Database batch operation failed")
                st.error(f"Database batch operation failed: {exc}")
            except Exception as exc:
                logger.exception("Unexpected batch automation failure")
                st.error(f"Batch automation failed: {exc}")

# --- TAB 3: MANAGE DUE DATES ---
with tab3:
    st.header("🗓️ Manage Due Dates")
    st.caption("Update individual deadlines or use bulk update across all records for live testing.")
    
    col_single, col_bulk = st.columns(2)
    
    # Single Student Update
    with col_single:
        st.subheader("👤 Individual Update")
        try:
            df_students = conn.query("SELECT id, student_name, due_date FROM Students ORDER BY student_name;", ttl="0m")
            if not df_students.empty:
                with st.form("single_update_form"):
                    student_map = dict(zip(df_students['student_name'], df_students['id']))
                    selected_student = st.selectbox("Select Student", list(student_map.keys()))
                    
                    curr_date = df_students[df_students['student_name'] == selected_student]['due_date'].iloc[0]
                    st.write(f"Current due date: **{curr_date}**")
                    
                    new_due_date = st.date_input("New Due Date", key="single_date_input")
                    submit_single = st.form_submit_button("Update Student")
                    
                    if submit_single:
                        try:
                            student_id = int(student_map[selected_student])
                            with conn.session as session:
                                session.execute(
                                    text("UPDATE Students SET due_date = :due_date, last_updated_by = :user WHERE id = :id"),
                                    {"due_date": new_due_date, "user": st.session_state["username"], "id": student_id}
                                )
                                session.commit()
                            st.success(f"Updated {selected_student}'s due date to {new_due_date}!")
                            st.cache_data.clear()
                        except SQLAlchemyError as exc:
                            logger.exception("Failed to update due date for %s", selected_student)
                            st.error(f"Database error while updating due date: {exc}")
                        except Exception as exc:
                            logger.exception("Unexpected error updating due date for %s", selected_student)
                            st.error(f"Unable to update due date: {exc}")
            else:
                st.warning("No records found.")
        except SQLAlchemyError as exc:
            logger.exception("Failed to load student list for due date management")
            st.error(f"Database error while loading student list: {exc}")
        except Exception as exc:
            logger.exception("Unexpected error loading student list for due date management")
            st.error(f"Error loading student list: {exc}")

    # Bulk Update Across the Board
    with col_bulk:
        st.subheader("⚡ Bulk Update (Testing Engine)")
        st.info("💡 Set all records at once to test the automated rules in Tab 2.")
        
        with st.form("bulk_update_form"):
            bulk_date = st.date_input("Set Date for ALL Records", key="bulk_date_input")
            submit_bulk = st.form_submit_button("Apply to All Students")
            
            if submit_bulk:
                try:
                    with conn.session as session:
                        session.execute(
                            text("UPDATE Students SET due_date = :bulk_date, last_updated_by = :user"),
                            {"bulk_date": bulk_date, "user": st.session_state["username"]}
                        )
                        session.commit()
                    st.success(f"Successfully updated ALL records to {bulk_date}!")
                    st.cache_data.clear()
                except SQLAlchemyError as exc:
                    logger.exception("Bulk due date update failed")
                    st.error(f"Database error during bulk update: {exc}")
                except Exception as exc:
                    logger.exception("Unexpected bulk due date update failure")
                    st.error(f"Bulk update failed: {exc}")

# --- TAB 4: STUDENT MANAGEMENT ---
with tab4:
    st.header("🧑‍🎓 Student Directory & Operations")
    
    st.subheader("Current Database View")
    try:
        df_students = conn.query("SELECT id, student_name, parent_phone, fee_amount, due_date, payment_status, franchise_name, last_updated_by FROM Students ORDER BY student_name;", ttl="0m")
        if not df_students.empty:
            st.dataframe(df_students, use_container_width=True, hide_index=True)
        else:
            st.info("No students found in the database.")
    except SQLAlchemyError as exc:
        logger.exception("Failed to load students for management tab")
        st.error(f"Database error while loading students: {exc}")
        df_students = pd.DataFrame()
    except Exception as exc:
        logger.exception("Unexpected error loading students for management tab")
        st.error(f"Error loading students: {exc}")
        df_students = pd.DataFrame()

    st.divider()
    st.subheader("Administrative Actions")
    
    action_tabs = st.tabs(["➕ Enroll Student", "✏️ Update Profile", "❌ Remove Student"])

    # CREATE 
    with action_tabs[0]:
        with st.form("add_student_form", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            with c1:
                new_name = st.text_input("Student Name")
                new_phone = st.text_input("Parent Phone (10 digits)")
            with c2:
                new_amount = st.number_input("Fee (₹)", min_value=100.0, value=1200.0)
                new_due_date = st.date_input("First Due Date")
            with c3:
                new_status = st.selectbox("Status", ["Pending", "Paid"])
                new_franchise = st.selectbox("Assign to Franchise", FRANCHISE_OPTIONS)
                
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
                                
                    except SQLAlchemyError as exc:
                        logger.exception("Failed to add student %s", new_name)
                        st.error(f"Database error while adding student: {exc}")
                    except Exception as exc:
                        logger.exception("Unexpected error adding student %s", new_name)
                        st.error(f"Error adding student: {exc}")

    # UPDATE
    with action_tabs[1]:
        if not df_students.empty:
            student_map = dict(zip(df_students['student_name'], df_students['id']))
            selected = st.selectbox("Select Student to Update", list(student_map.keys()))
            
            curr_data = df_students[df_students['student_name'] == selected].iloc[0]
            curr_franchise = curr_data.get('franchise_name', 'Company HQ')
            franchise_idx = FRANCHISE_OPTIONS.index(curr_franchise) if curr_franchise in FRANCHISE_OPTIONS else 0
            
            with st.form("update_student_form"):
                c1, c2, c3 = st.columns(3)
                with c1:
                    upd_phone = st.text_input("Phone", value=curr_data['parent_phone'])
                    upd_amount = st.number_input("Fee (₹)", value=float(curr_data['fee_amount']))
                with c2:
                    upd_date = st.date_input("Due Date", value=pd.to_datetime(curr_data['due_date']))
                    upd_status = st.selectbox("Status", ["Pending", "Paid"], index=0 if curr_data['payment_status'] == "Pending" else 1)
                with c3:
                    upd_franchise = st.selectbox("Franchise", FRANCHISE_OPTIONS, index=franchise_idx)
                
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
                    except SQLAlchemyError as exc:
                        logger.exception("Failed to update student %s", selected)
                        st.error(f"Database error while updating student: {exc}")
                    except Exception as exc:
                        logger.exception("Unexpected error updating student %s", selected)
                        st.error(f"Error updating student: {exc}")
        else:
            st.info("No records available to update.")

    # DELETE
    with action_tabs[2]:
        if st.session_state["role"] == "Franchise":
            st.error("🚫 Access Denied: Franchise users cannot permanently delete records. Please contact Company Admin.")
        else:
            if not df_students.empty:
                student_map = dict(zip(df_students['student_name'], df_students['id']))
                del_selected = st.selectbox("Select Student to Permanently Delete", list(student_map.keys()))
                
                st.warning(f"You are about to permanently remove **{del_selected}** from the database. This action cannot be undone.")
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
                    except SQLAlchemyError as exc:
                        logger.exception("Failed to delete student %s", del_selected)
                        st.error(f"Database error while deleting student: {exc}")
                    except Exception as exc:
                        logger.exception("Unexpected error deleting student %s", del_selected)
                        st.error(f"Error deleting student: {exc}")
            else:
                st.info("No records available to delete.")
