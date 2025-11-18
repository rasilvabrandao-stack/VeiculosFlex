#!/usr/bin/env bash
# Install system dependencies for Pillow
apt-get update && apt-get install -y \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
python -m pip install --upgrade pip

# Install Python dependencies with no cache to avoid old cached source builds
pip install --no-cache-dir -r requirements.txt
