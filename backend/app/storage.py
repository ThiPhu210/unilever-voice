import os
import shutil
import threading

AUDIO_DIR = os.getenv("AUDIO_DIR", "data/audio")
AUDIO_BUCKET = os.getenv("AUDIO_BUCKET", "")
AUDIO_PREFIX = os.getenv("AUDIO_PREFIX", "audio").strip("/")
PRESIGN_TTL = int(os.getenv("AUDIO_PRESIGN_TTL", "900")) 
os.makedirs(AUDIO_DIR, exist_ok=True)

_client = None
_lock = threading.Lock()


def s3_enabled() -> bool:
    return bool(AUDIO_BUCKET)


def is_s3(ref: str | None) -> bool:
    return bool(ref) and ref.startswith("s3://")


def _s3():
    global _client
    with _lock:
        if _client is None:
            import boto3
            from botocore.config import Config
            region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or None
            _client = boto3.client("s3", region_name=region, config=Config(signature_version="s3v4", retries={"max_attempts": 3}))
        return _client


def _split(ref: str) -> tuple[str, str]:
    bucket, _, key = ref[len("s3://"):].partition("/")
    return bucket, key


def make_key(sa_id: str, session_id: str, created_at: str, ext: str) -> str:
    """audio/{sa_id}/{yyyy}/{mm}/{session_id}.m4a — gom theo SA và tháng để tra cứu / áp chính sách lưu trữ."""
    y, m = (created_at[:4] or "0000"), (created_at[5:7] or "00")
    safe_sa = "".join(ch for ch in (sa_id or "unknown") if ch.isalnum() or ch in "-_") or "unknown"
    return f"{AUDIO_PREFIX}/{safe_sa}/{y}/{m}/{session_id}{ext}"


def put(local_path: str, key: str, content_type: str = "audio/mp4") -> str:
    """Lưu file, trả về tham chiếu. S3: mã hoá SSE-S3, rồi xoá bản local. Local: chuyển vào AUDIO_DIR."""
    if s3_enabled():
        _s3().upload_file(local_path, AUDIO_BUCKET, key,
                          ExtraArgs={"ContentType": content_type, "ServerSideEncryption": "AES256"})
        try:
            os.remove(local_path)
        except OSError:
            pass
        return f"s3://{AUDIO_BUCKET}/{key}"
    dst = os.path.join(AUDIO_DIR, os.path.basename(key))
    if os.path.abspath(local_path) != os.path.abspath(dst):
        shutil.move(local_path, dst)
    return dst


def presigned_url(ref: str, filename: str | None = None, ttl: int = PRESIGN_TTL) -> str:
    bucket, key = _split(ref)
    params = {"Bucket": bucket, "Key": key}
    if filename:
        params["ResponseContentDisposition"] = f'inline; filename="{filename}"'
    return _s3().generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)


def download(ref: str, dst: str) -> str:
    """Tải về file local (khi cần chạy ASR/diarization trên audio đã nằm ở S3)."""
    bucket, key = _split(ref)
    _s3().download_file(bucket, key, dst)
    return dst


def exists(ref: str | None) -> bool:
    if not ref:
        return False
    if is_s3(ref):
        return True   # không gọi S3 chỉ để kiểm tra tồn tại; lỗi sẽ lộ ra khi cấp URL / tải
    return os.path.exists(ref)