#!/usr/bin/env bash
set -euo pipefail

export PATH="${HOME}/.local/bin:${PATH}"

POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-checknmate}"
POSTGRES_USER="${POSTGRES_USER:-checknmate}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-devpassword}"

ensure_local_postgres() {
  if ! command -v pg_isready >/dev/null 2>&1; then
    return 0
  fi

  if ! pg_isready -q 2>/dev/null; then
    sudo pg_ctlcluster 16 main start 2>/dev/null || sudo service postgresql start
  fi

  sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
    CREATE USER ${POSTGRES_USER} WITH PASSWORD '${POSTGRES_PASSWORD}' CREATEDB;
  END IF;
END
\$\$;
SELECT 'CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}')\gexec
SQL

  sudo -u postgres psql -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS Students (
  id SERIAL PRIMARY KEY,
  student_name TEXT NOT NULL,
  parent_phone TEXT NOT NULL,
  fee_amount DOUBLE PRECISION NOT NULL,
  due_date DATE NOT NULL,
  payment_status TEXT NOT NULL DEFAULT 'Pending'
);
SQL

  sudo -u postgres psql -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 <<SQL
GRANT ALL PRIVILEGES ON TABLE students TO ${POSTGRES_USER};
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ${POSTGRES_USER};
SQL
}

write_streamlit_secrets() {
  mkdir -p /workspace/.streamlit
  cat > /workspace/.streamlit/secrets.toml <<EOF
admin_password = "${ADMIN_PASSWORD:-devadmin123}"

[connections.postgresql]
dialect = "postgresql"
host = "${POSTGRES_HOST}"
port = ${POSTGRES_PORT}
database = "${POSTGRES_DB}"
username = "${POSTGRES_USER}"
password = "${POSTGRES_PASSWORD}"

[razorpay]
key_id = "${RAZORPAY_KEY_ID:-rzp_test_placeholder}"
key_secret = "${RAZORPAY_KEY_SECRET:-rzp_test_secret_placeholder}"

[twilio]
account_sid = "${TWILIO_ACCOUNT_SID:-ACplaceholder}"
auth_token = "${TWILIO_AUTH_TOKEN:-placeholder_token}"
sandbox_number = "${TWILIO_SANDBOX_NUMBER:-whatsapp:+14155238886}"
EOF
}

start_streamlit() {
  if curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
    echo "Streamlit already running on port 8501"
    return 0
  fi

  nohup streamlit run /workspace/app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --browser.gatherUsageStats false \
    > /tmp/streamlit.log 2>&1 &

  for _ in $(seq 1 45); do
    if curl -sf "http://127.0.0.1:8501/_stcore/health" >/dev/null 2>&1; then
      echo "Streamlit ready on port 8501"
      return 0
    fi
    sleep 1
  done

  echo "Streamlit failed to start within 45s" >&2
  tail -30 /tmp/streamlit.log >&2 || true
  return 1
}

if [ "${POSTGRES_HOST}" = "localhost" ] || [ "${POSTGRES_HOST}" = "127.0.0.1" ]; then
  ensure_local_postgres
fi

write_streamlit_secrets
start_streamlit
