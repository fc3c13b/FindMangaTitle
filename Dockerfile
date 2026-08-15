FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Label
ARG VERSION
LABEL version="${VERSION}"

# Expose port
EXPOSE 8000

# Run API server
CMD ["python", "api_server.py"]