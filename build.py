#!/usr/bin/env python3
"""
build.py — Empacota GIOW Downloader para Windows

Pré-requisitos (rodar no Windows ou via CI):
    pip install pyinstaller yt-dlp flask flask-cors
    npm install

Uso:
    python build.py

Resultado:
    dist/GIOW-Downloader-1.0.0.exe  (portátil, ~300MB)
"""

import os
import sys
import shutil
import subprocess
import platform

ROOT = os.path.dirname(os.path.abspath(__file__))


def run(cmd, cwd=None):
    print(f"\n>>> {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, check=True)
    return result


def step1_pyinstaller():
    """Empacota server.py + yt-dlp + ffmpeg num executável."""
    print("\n" + "="*50)
    print("STEP 1: PyInstaller — empacotando servidor Python")
    print("="*50)

    # Localiza yt-dlp e ffmpeg
    ytdlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

    if not ytdlp:
        print("ERRO: yt-dlp não encontrado. Execute: pip install yt-dlp[default]")
        sys.exit(1)
    if not ffmpeg:
        print("AVISO: ffmpeg não encontrado. Downloads sem mux de áudio.")
        ffmpeg_args = []
    else:
        ffmpeg_args = [f"--add-binary={ffmpeg};."]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",           # pasta com executável + dependências
        "--name", "server",
        "--distpath", os.path.join(ROOT, "python-dist"),
        "--workpath", os.path.join(ROOT, "build", "pyinstaller"),
        "--specpath", os.path.join(ROOT, "build"),
        "--noconsole",        # sem janela de console no Windows
        "--clean",
        f"--add-binary={ytdlp};.",   # inclui yt-dlp
    ] + ffmpeg_args + [
        os.path.join(ROOT, "python", "server.py"),
    ]

    run(cmd)
    print("✓ PyInstaller concluído")


def step2_npm_install():
    """Instala dependências Node.js."""
    print("\n" + "="*50)
    print("STEP 2: npm install")
    print("="*50)
    run(["npm", "install"], cwd=ROOT)
    print("✓ npm install concluído")


def step3_electron_build():
    """Empacota Electron + Python num .exe portátil."""
    print("\n" + "="*50)
    print("STEP 3: electron-builder — gerando .exe portátil")
    print("="*50)

    # Copia arquivos do front para src/
    for f in ["index.html", "script.js", "style.css"]:
        src = os.path.join(ROOT, "src", f)
        if not os.path.exists(src):
            print(f"AVISO: {f} não encontrado em src/")

    run(["npm", "run", "build"], cwd=ROOT)
    print("✓ electron-builder concluído")


def main():
    print("GIOW Downloader — Build Script")
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.system()}")
    print(f"Root: {ROOT}")

    if platform.system() != "Windows":
        print("\nAVISO: Para gerar .exe para Windows, execute este script no Windows")
        print("ou use o GitHub Actions com runner windows-latest")

    step1_pyinstaller()
    step2_npm_install()
    step3_electron_build()

    print("\n" + "="*50)
    print("✓ BUILD CONCLUÍDO!")
    print(f"  Arquivo: dist/GIOW-Downloader-1.0.0.exe")
    print("="*50)


if __name__ == "__main__":
    main()
