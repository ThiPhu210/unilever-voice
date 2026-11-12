"""Nén audio hội thoại trước khi lưu. App gửi WAV 16 kHz mono (định dạng duy nhất bộ nhận dạng của HĐH nhận làm file ghi âm),
~1.9 MB/phút; nén sang AAC mono thì còn ~0.18 MB/phút (24 kbps) mà vẫn nghe lại rõ lời và mọi trình duyệt/điện thoại đều phát được.
"""
import os
import shutil
import subprocess

BITRATE = os.getenv("AUDIO_BITRATE", "24k")
FFMPEG = shutil.which("ffmpeg")


def compress(src: str, dst_base: str) -> tuple[str, str]:
    """Nén `src` thành m4a (AAC-LC, mono, 16 kHz). Trả về (đường_dẫn, phần_mở_rộng).
    ffmpeg thiếu hoặc lỗi -> giữ nguyên file gốc (không mất dữ liệu), đổi tên theo đuôi gốc."""
    src_ext = os.path.splitext(src)[1] or ".bin"
    if FFMPEG:
        dst = dst_base + ".m4a"
        try:
            subprocess.run(
                [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "aac", "-b:a", BITRATE, "-movflags", "+faststart", dst],
                check=True, timeout=120)
            if os.path.getsize(dst) > 0:
                os.remove(src)
                return dst, ".m4a"
        except (subprocess.SubprocessError, OSError) as e:
            print("audio compress failed, keep original:", e)
            if os.path.exists(dst):
                os.remove(dst)
    keep = dst_base + src_ext
    os.replace(src, keep)
    return keep, src_ext


def duration_seconds(path: str) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    try:
        out = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nk=1:nw=1", path],
                             capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        return float(out)
    except (subprocess.SubprocessError, ValueError, OSError):
        return None
