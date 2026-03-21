#!/usr/bin/env python3
"""
build.py — Empacota GIOW Downloader (Windows, macOS, Linux)

Pré-requisitos:
    pip install pyinstaller yt-dlp flask flask-cors
    npm install

Uso:
    python build.py              # detecta plataforma automaticamente
    python build.py --win        # força Windows (cross-compile não funciona para exe)
    python build.py --mac        # macOS
    python build.py --linux      # Linux AppImage

Resultado:
    dist/GIOW-Downloader-1.0.0-win.exe       (Windows portátil)
    dist/GIOW-Downloader-1.0.0-mac.dmg       (macOS)
    dist/GIOW-Downloader-1.0.0-linux.AppImage (Linux)
"""

import os
import sys
import shutil
import subprocess
import platform
import argparse

ROOT = os.path.dirname(os.path.abspath(__file__))
IS_WIN = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"


def run(cmd, cwd=None):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd or ROOT, check=True)
    return result


def step1_pyinstaller():
    """Empacota server.py + yt-dlp + ffmpeg num executável nativo."""
    print("\n" + "="*50)
    print("STEP 1: PyInstaller — empacotando servidor Python")
    print("="*50)

    ytdlp = shutil.which("yt-dlp") or shutil.which("yt-dlp.exe")
    ffmpeg = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")

    if not ytdlp:
        print("ERRO: yt-dlp não encontrado. Execute: pip install yt-dlp[default]")
        sys.exit(1)

    print(f"  yt-dlp  : {ytdlp}")
    print(f"  ffmpeg  : {ffmpeg or 'NÃO ENCONTRADO (downloads sem mux de áudio)'}")
    print(f"  plataforma: {platform.system()}")

    # Em Windows o separador do --add-binary é ";" em macOS/Linux é ":"
    sep = ";" if IS_WIN else ":"

    add_binaries = [f"--add-binary={ytdlp}{sep}."]
    if ffmpeg:
        add_binaries.append(f"--add-binary={ffmpeg}{sep}.")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir",
        "--name", "server",
        "--distpath", os.path.join(ROOT, "python-dist"),
        "--workpath", os.path.join(ROOT, "build", "pyinstaller"),
        "--specpath", os.path.join(ROOT, "build"),
        "--clean",
    ]

    # --noconsole só faz sentido no Windows (esconde a janela CMD)
    # No macOS/Linux não tem efeito negativo mas evita warnings
    if IS_WIN:
        cmd.append("--noconsole")

    cmd += add_binaries
    cmd.append(os.path.join(ROOT, "python", "server.py"))

    run(cmd)

    # Valida que o executável foi gerado
    exe_name = "server.exe" if IS_WIN else "server"
    exe_path = os.path.join(ROOT, "python-dist", "server", exe_name)
    if not os.path.exists(exe_path):
        print(f"ERRO: {exe_path} não foi gerado pelo PyInstaller!")
        sys.exit(1)

    # Garante permissão de execução em macOS/Linux
    if not IS_WIN:
        os.chmod(exe_path, 0o755)
        print(f"  chmod 755: {exe_path}")

    print(f"✓ PyInstaller concluído → {exe_path}")


def step2_copy_server():
    """Copia python-dist/server → server/ (pasta incluída pelo electron-builder)."""
    print("\n" + "="*50)
    print("STEP 2: Copiando servidor para pasta 'server/'")
    print("="*50)

    src = os.path.join(ROOT, "python-dist", "server")
    dst = os.path.join(ROOT, "server")

    if os.path.exists(dst):
        print(f"  Removendo server/ anterior...")
        shutil.rmtree(dst)

    shutil.copytree(src, dst)

    exe_name = "server.exe" if IS_WIN else "server"
    exe_path = os.path.join(dst, exe_name)

    if not os.path.exists(exe_path):
        print(f"ERRO: {exe_path} não encontrado após cópia!")
        sys.exit(1)

    print(f"✓ Copiado → {dst}")
    print(f"  {exe_name} presente: {os.path.exists(exe_path)}")


def step3_npm_install():
    """Instala dependências Node.js."""
    print("\n" + "="*50)
    print("STEP 3: npm install")
    print("="*50)
    npm = "npm.cmd" if IS_WIN else "npm"
    run([npm, "install"], cwd=ROOT)
    print("✓ npm install concluído")


def step4_electron_build(target=None):
    """Empacota Electron num executável/pacote portátil."""
    print("\n" + "="*50)
    print("STEP 4: electron-builder")
    print("="*50)

    npm = "npm.cmd" if IS_WIN else "npm"

    if target == "win":
        run([npm, "run", "build:win"], cwd=ROOT)
    elif target == "mac":
        run([npm, "run", "build:mac"], cwd=ROOT)
    elif target == "linux":
        run([npm, "run", "build:linux"], cwd=ROOT)
    else:
        # Detecta automaticamente
        if IS_WIN:
            run([npm, "run", "build:win"], cwd=ROOT)
        elif IS_MAC:
            run([npm, "run", "build:mac"], cwd=ROOT)
        else:
            run([npm, "run", "build:linux"], cwd=ROOT)

    print("✓ electron-builder concluído")


def main():
    parser = argparse.ArgumentParser(description="GIOW Downloader Build Script")
    parser.add_argument("--win", action="store_true", help="Força build Windows")
    parser.add_argument("--mac", action="store_true", help="Força build macOS")
    parser.add_argument("--linux", action="store_true", help="Força build Linux")
    parser.add_argument("--skip-pyinstaller", action="store_true",
                        help="Pula o PyInstaller (usa server/ existente)")
    args = parser.parse_args()

    target = None
    if args.win:
        target = "win"
    elif args.mac:
        target = "mac"
    elif args.linux:
        target = "linux"

    print("GIOW Downloader — Build Script")
    print(f"Python: {sys.version}")
    print(f"Platform: {platform.system()} {platform.machine()}")
    print(f"Root: {ROOT}")
    print(f"Target: {target or 'auto'}")

    if not args.skip_pyinstaller:
        step1_pyinstaller()
        step2_copy_server()
    else:
        print("\n⏭  Pulando PyInstaller (--skip-pyinstaller)")
        exe_name = "server.exe" if IS_WIN else "server"
        exe_path = os.path.join(ROOT, "server", exe_name)
        if not os.path.exists(exe_path):
            print(f"ERRO: {exe_path} não encontrado. Rode sem --skip-pyinstaller primeiro.")
            sys.exit(1)

    step3_npm_install()
    step4_electron_build(target)

    print("\n" + "="*50)
    print("✓ BUILD CONCLUÍDO!")
    print(f"  Saída em: dist/")
    print("="*50)


if __name__ == "__main__":
    main()
