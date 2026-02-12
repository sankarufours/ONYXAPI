FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# system deps needed by some image processing packages (opencv runtime libs)
RUN apt-get update \
     && apt-get install -y --no-install-recommends \
         build-essential \
         ca-certificates \
         libglib2.0-0 \
         libsm6 \
         libxrender1 \
         libxext6 \
         libgl1 \
    && rm -rf /var/lib/apt/lists/*

# copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy package
COPY . .

# expose the API port
EXPOSE 8000

# run uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
