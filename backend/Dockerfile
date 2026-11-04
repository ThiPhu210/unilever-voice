FROM python:3.11-slim
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Model nhận diện giọng (CAM++, ~27MB) tải sẵn lúc build
RUN mkdir -p /srv/models && python -c "import urllib.request as u; u.urlretrieve('https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx','/srv/models/speaker.onnx')"
ENV SPEAKER_MODEL=/srv/models/speaker.onnx
ENV DB_PATH=/data/app.db AUDIO_DIR=/data/audio HF_HOME=/data/hf
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
