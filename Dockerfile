# Use the official lightweight Python image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the dependencies file and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the webhook receiver script into the container
COPY webhook_service.py .

# Expose the port that Google Cloud Run expects
EXPOSE 8080

# Command to start the FastAPI server using Uvicorn
CMD ["uvicorn", "webhook_service:app", "--host", "0.0.0.0", "--port", "8080"]
