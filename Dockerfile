# Use slim Python image
FROM python:3.10-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Copy dependency file and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Expose the FastAPI port
EXPOSE 8000

# Run the FastAPI app (adjusted for your folder structure)
CMD ["uvicorn", "sampatti.main:app", "--host", "0.0.0.0", "--port", "8000"]
