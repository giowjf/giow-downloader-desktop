"""
GIOW Downloader — Servidor local para o executável desktop.
Roda em localhost:5001, serve o Electron com analyze e download direto.
Sem proxy, sem CORS — download vai direto do YouTube para o disco do usuário.
"""

import os
import sys
import json
import time
import hashlib
import subprocess
import traceback

# ── Log em arquivo para debug no .exe empacotado ─────────────────────────────
# PyInstaller redireciona stdout/stderr para None em --noconsole
# Escrever em arquivo garante que erros de startup sejam visíveis

LOG_PATH = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "giow-server.log")

class Tee:
    """Espelha writes para arquivo + stream original (se existir)."""
    def __init__(self, original):
        self._original = original
        try:
            self._file = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        except Exception:
            self._file = None

    def write(self, data):
        if self._file:
            try: self._file.write(data)
            except Exception: pass
        if self._original:
            try: self._original.write(data)
            except Exception: pass

    def flush(self):
        if self._file:
            try: self._file.flush()
            except Exception: pass
        if self._original:
            try: self._original.flush()
            except Exception: pass

    def fileno(self):
        if self._original:
            try: return self._original.fileno()
            except Exception: pass
        raise OSError("no fileno")

sys.stdout = Tee(sys.stdout)
sys.stderr = Tee(sys.stderr)

print(f"[server] Iniciando — Python {sys.version}")
print(f"[server] Log: {LOG_PATH}")
print(f"[server] frozen: {getattr(sys, 'frozen', False)}")
if getattr(sys, "frozen", False):
    print(f"[server] _MEIPASS: {sys._MEIPASS}")

try:
    from flask import Flask, request, jsonify, Response
    from flask_cors import CORS
    print("[server] Flask importado OK")
except Exception as e:
    print(f"[server] ERRO ao importar Flask: {e}")
    traceback.print_exc()
    sys.exit(1)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}},
     allow_headers=["Content-Type"], methods=["GET", "POST", "OPTIONS"])

PORT = int(os.environ.get("GIOW_PORT", 5001))

# ── Cache ────────────────────────────────────────────────────────────────────
_analyze_cache = {}
ANALYZE_TTL = 300  # 5 minutos


# ── Utilitários ──────────────────────────────────────────────────────────────

def get_ytdlp_path():
    """Localiza o yt-dlp bundled ou no PATH."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
        candidates = [
            os.path.join(base, "yt-dlp.exe"),
            os.path.join(base, "yt-dlp"),
        ]
        for p in candidates:
            if os.path.exists(p):
                print(f"[server] yt-dlp encontrado: {p}")
                return p
        print(f"[server] AVISO: yt-dlp não encontrado em _MEIPASS={base}")
        print(f"[server] Conteúdo de _MEIPASS: {os.listdir(base)[:20]}")
    return "yt-dlp"


def get_ffmpeg_path():
    """Localiza o ffmpeg bundled ou no PATH."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
        for p in [os.path.join(base, "ffmpeg.exe"), os.path.join(base, "ffmpeg")]:
            if os.path.exists(p):
                return p
    return "ffmpeg"


def run_ytdlp(args, timeout=60):
    """Executa yt-dlp com os argumentos fornecidos."""
    ytdlp = get_ytdlp_path()
    cmd = [ytdlp] + args
    print(f"[ytdlp] cmd: {cmd[0]}")

    # Esconde janela CMD no Windows
    kwargs = {}
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        **kwargs,
    )
    print(f"[ytdlp] returncode: {result.returncode}")
    if result.stdout: print(f"[ytdlp] stdout: {result.stdout[:300]}")
    if result.stderr: print(f"[ytdlp] stderr: {result.stderr[:500]}")
    return result


# ── Extração ─────────────────────────────────────────────────────────────────

def extract_info(url):
    """Extrai metadados e formatos via yt-dlp CLI."""
    url_key = hashlib.md5(url.encode()).hexdigest()

    if url_key in _analyze_cache:
        cached, cached_at = _analyze_cache[url_key]
        if time.time() - cached_at < ANALYZE_TTL:
            print(f"[analyze] Cache hit")
            return cached
        del _analyze_cache[url_key]

    print(f"[analyze] Extraindo: {url[:60]}")
    t0 = time.time()

    result = run_ytdlp([
        "--dump-single-json",
        "--no-check-certificate",
        "--ignore-no-formats-error",
        "--no-playlist",
        "--extractor-args", "youtube:player_client=web+formats=missing_pot",
        "--quiet",
        url,
    ])

    if result.returncode != 0:
        raise ValueError(f"yt-dlp erro: {result.stderr[-300:]}")

    lines = [l for l in result.stdout.strip().splitlines() if l.startswith("{")]
    if not lines:
        raise ValueError("yt-dlp retornou saída vazia")

    info = json.loads(lines[-1])
    elapsed = round(time.time() - t0, 2)
    print(f"[analyze] OK em {elapsed}s")

    _analyze_cache[url_key] = (info, time.time())
    return info


def is_direct_url(f):
    """Filtra apenas URLs diretas — não manifests/HLS/mhtml."""
    url = f.get("url") or ""
    protocol = f.get("protocol") or ""
    ext = f.get("ext") or ""
    if ext in ("m3u8", "mhtml"):
        return False
    if protocol in ("m3u8", "m3u8_native", "dash", "http_dash_segments"):
        return False
    if "m3u8" in url or ".m3u8" in url:
        return False
    if url.startswith("manifest"):
        return False
    return url.startswith("http")


def build_formats(info):
    """Monta lista de formatos para o front."""
    formats = info.get("formats") or []

    video_fmts = [f for f in formats
                  if is_direct_url(f)
                  and (f.get("vcodec") or "none") != "none"
                  and (f.get("height") or 0) > 0]

    audio_fmts = [f for f in formats
                  if is_direct_url(f)
                  and (f.get("acodec") or "none") != "none"
                  and (f.get("vcodec") or "none") == "none"]

    best_audio = max(audio_fmts, key=lambda f: f.get("abr") or 0) if audio_fmts else None

    seen = set()
    result = []

    for f in sorted(video_fmts, key=lambda f: f.get("height") or 0, reverse=True):
        height = f.get("height") or 0
        ext = f.get("ext") or "mp4"
        resolution = f.get("resolution") or f"{height}p"
        key = (ext, resolution)
        if key in seen:
            continue
        seen.add(key)

        has_audio = (f.get("acodec") or "none") != "none"
        entry = {
            "format_id": f.get("format_id"),
            "ext": ext,
            "resolution": resolution,
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "fps": f.get("fps"),
            "video_url": f.get("url"),
            "has_audio": has_audio,
        }
        if not has_audio and best_audio:
            entry["audio_url"] = best_audio.get("url")
            entry["audio_ext"] = best_audio.get("ext", "m4a")

        result.append(entry)

    if best_audio:
        result.append({
            "format_id": "mp3-direct",
            "ext": "mp3",
            "resolution": "audio only",
            "filesize": best_audio.get("filesize"),
            "fps": None,
            "video_url": best_audio.get("url"),
            "has_audio": True,
            "is_audio_only": True,
        })

    return result


# ── Rotas ────────────────────────────────────────────────────────────────────

@app.route("/")
def health():
    return jsonify({
        "status": "running",
        "mode": "desktop",
        "port": PORT,
    })


@app.route("/analyze", methods=["POST", "OPTIONS"])
def analyze():
    if request.method == "OPTIONS":
        return "", 204

    data = request.json
    url = data.get("url") if data else None
    if not url:
        return jsonify({"error": "missing url"}), 400

    try:
        t0 = time.time()
        info = extract_info(url)
        formats = build_formats(info)
        elapsed = round(time.time() - t0, 2)

        return jsonify({
            "title": info.get("title"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "uploader": info.get("uploader"),
            "formats": formats,
            "elapsed": elapsed,
            "urls_need_proxy": False,
        })
    except Exception as e:
        print(f"[analyze] ERRO: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/download", methods=["POST", "OPTIONS"])
def download():
    if request.method == "OPTIONS":
        return "", 204

    data = request.json
    url = data.get("url")
    format_id = data.get("format_id")
    mode = data.get("mode", "mp4")
    output_path = data.get("output_path")

    if not url or not output_path:
        return jsonify({"error": "missing url or output_path"}), 400

    try:
        ytdlp = get_ytdlp_path()
        ffmpeg = get_ffmpeg_path()

        if mode == "mp3":
            fmt = "bestaudio/best"
        elif format_id and format_id != "mp3":
            fmt = (f"{format_id}+bestaudio[ext=m4a]/"
                   f"{format_id}+bestaudio/"
                   f"{format_id}/"
                   "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best")
        else:
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"

        cmd = [
            ytdlp,
            "--no-check-certificate",
            "--no-playlist",
            "--format", fmt,
            "--ffmpeg-location", os.path.dirname(ffmpeg),
            "--output", output_path,
            "--quiet",
            "--progress",
        ]

        if mode == "mp3":
            cmd += [
                "--extract-audio",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
            ]

        cmd.append(url)

        print(f"[download] Iniciando: {url[:60]}")
        dl_kwargs = {}
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            dl_kwargs["startupinfo"] = si
            dl_kwargs["creationflags"] = 0x08000000
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, **dl_kwargs)
        if result.stderr: print(f"[download] stderr: {result.stderr[:500]}")

        if result.returncode != 0:
            raise ValueError(result.stderr[-300:])

        print(f"[download] Concluído: {output_path}")
        return jsonify({"success": True, "path": output_path})

    except Exception as e:
        print(f"[download] ERRO: {e}")
        return jsonify({"error": str(e)}), 500


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"[server] GIOW Desktop iniciando na porta {PORT}...")
    try:
        app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True)
    except Exception as e:
        print(f"[server] ERRO FATAL ao iniciar Flask: {e}")
        traceback.print_exc()
        sys.exit(1)
