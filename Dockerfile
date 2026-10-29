# Dockerfile
# Builds the CyberSentinel Flask application image.
# Uses python:3.12-slim to keep the image small.

FROM python:3.12-slim

# Set working directory inside the container
WORKDIR /app

# Copy and install dependencies first (Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project into the container
COPY . .

# Expose the Flask port
EXPOSE 5000

# Run the app directly (no Werkzeug reloader in production/Docker)
CMD ["python", "-m", "app.main"]
