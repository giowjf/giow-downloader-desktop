"""
Suite de testes — giow-downloader-desktop
Valida estrutura, código e lógica antes do build.

Uso:
    python test_suite.py
"""

import sys, os, json, subprocess

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"
BOLD = "\033[1m"; RESET = "\033[0m"

def ok(m):   print(f"  {GREEN}✓{RESET} {m}")
def fail(m): print(f"  {RED}✗{RESET} {m}")
def warn(m): print(f"  {YELLOW}~{RESET} {m}")
def section(t): print(f"\n{BOLD}{'─'*52}{RESET}\n{BOLD}{t}{RESET}")

passed = failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1; ok(name)
    else:
        failed += 1; fail(name + (f"\n    → {detail}" if detail else ""))

ROOT = os.path.dirname(os.path.abspath(__file__))

# ── BLOCO 1: Estrutura de arquivos ───────────────────────────────────────────

def test_structure():
    section("1. Estrutura de arquivos")
    required = [
        "src/main.js",
        "src/preload.js",
        "src/script.js",
        "src/index.html",
        "src/style.css",
        "python/server.py",
        "package.json",
        ".github/workflows/build.yml",
    ]
    for f in required:
        path = os.path.join(ROOT, f)
        check(f"Arquivo {f} existe", os.path.exists(path))

    check("build.yml NÃO está na raiz (só em .github/workflows/)",
          not os.path.exists(os.path.join(ROOT, "build.yml")))


# ── BLOCO 2: Sintaxe ────────────────────────────────────────────────────────

def test_syntax():
    section("2. Sintaxe dos arquivos")

    r = subprocess.run(["python3", "-m", "py_compile",
                        os.path.join(ROOT, "python/server.py")],
                       capture_output=True)
    check("python/server.py sintaxe válida", r.returncode == 0,
          r.stderr.decode()[:200])

    for f in ["src/main.js", "src/preload.js", "src/script.js"]:
        r = subprocess.run(["node", "--check", os.path.join(ROOT, f)],
                           capture_output=True)
        check(f"{f} sintaxe válida", r.returncode == 0,
              r.stderr.decode()[:200])


# ── BLOCO 3: package.json ────────────────────────────────────────────────────

def test_package_json():
    section("3. package.json")

    pkg = json.loads(open(os.path.join(ROOT, "package.json")).read())

    check("main aponta para src/main.js",
          pkg.get("main") == "src/main.js")
    check("electron nas devDependencies",
          "electron" in pkg.get("devDependencies", {}))
    check("electron-builder nas devDependencies",
          "electron-builder" in pkg.get("devDependencies", {}))
    check("script build existe",
          "build" in pkg.get("scripts", {}))

    build = pkg.get("build", {})
    check("appId configurado",
          bool(build.get("appId")))
    check("target portable configurado",
          any(t.get("target") == "portable"
              for t in build.get("win", {}).get("target", [])))
    check("files inclui src/**/*",
          "src/**/*" in build.get("files", []))

    # extraResources é o padrão correto para binários externos
    extra = build.get("extraResources", [])
    has_server_extra = any(
        isinstance(e, dict) and e.get("from", "").startswith("server")
        for e in extra
    )
    check("extraResources configura server/ corretamente",
          has_server_extra,
          "extraResources deve copiar server/ → resources/server/")

    check("--publish never nos scripts de build",
          all("--publish never" in s
              for k, s in pkg.get("scripts", {}).items()
              if k.startswith("build")),
          "Sem --publish never o electron-builder tenta publicar no CI e falha")

    check("Sem icon.ico (arquivo não existe)",
          "icon" not in build.get("win", {}),
          "Remover referência ao icon.ico ou criar o arquivo")


# ── BLOCO 4: main.js ────────────────────────────────────────────────────────

def test_main_js():
    section("4. src/main.js")
    content = open(os.path.join(ROOT, "src/main.js")).read()

    check("Usa process.resourcesPath para localizar server",
          "process.resourcesPath" in content,
          "O servidor deve ser buscado em resourcesPath (extraResources)")
    check("Busca server/ dentro de resourcesPath",
          'path.join(process.resourcesPath, "server"' in content,
          "extraResources coloca server/ em resources/server/")
    check("getPythonExe() implementada",
          "function getPythonExe" in content)
    check("startPythonServer() implementada",
          "function startPythonServer" in content)
    check("IPC show-save-dialog implementado",
          "show-save-dialog" in content)
    check("IPC get-api-url implementado",
          "get-api-url" in content)
    check("windowsHide configurado",
          "windowsHide" in content)
    check("webSecurity: false para permitir fetch local",
          "webSecurity" in content and "false" in content)
    check("preload.js referenciado",
          "preload.js" in content)


# ── BLOCO 5: preload.js ──────────────────────────────────────────────────────

def test_preload_js():
    section("5. src/preload.js")
    content = open(os.path.join(ROOT, "src/preload.js")).read()

    check("contextBridge usado (segurança)",
          "contextBridge" in content)
    check("electronAPI exposto",
          "electronAPI" in content)
    check("saveFile exposto",
          "saveFile" in content)
    check("getApiUrl exposto",
          "getApiUrl" in content)
    check("isDesktop: true exposto",
          "isDesktop" in content)


# ── BLOCO 6: server.py ──────────────────────────────────────────────────────

def test_server_py():
    section("6. python/server.py")
    content = open(os.path.join(ROOT, "python/server.py")).read()

    check("Flask importado",
          "from flask import" in content)
    check("Rota / (health) existe",
          '@app.route("/")' in content)
    check("Rota /analyze existe",
          '@app.route("/analyze"' in content)
    check("Rota /download existe",
          '@app.route("/download"' in content)
    check("PyInstaller frozen detectado (sys.frozen ou getattr frozen)",
          "sys.frozen" in content or 'getattr(sys, "frozen"' in content,
          "Necessário para encontrar yt-dlp bundled")
    check("get_ytdlp_path() implementada",
          "def get_ytdlp_path" in content)
    check("get_ffmpeg_path() implementada",
          "def get_ffmpeg_path" in content)
    check("Porta configurável via env GIOW_PORT",
          "GIOW_PORT" in content)
    check("threaded=True no Flask",
          "threaded=True" in content,
          "Necessário para não bloquear durante download")
    check("Cache de análise implementado",
          "_analyze_cache" in content)


# ── BLOCO 7: build.yml ───────────────────────────────────────────────────────

def test_build_yml():
    section("7. .github/workflows/build.yml")
    content = open(os.path.join(ROOT, ".github/workflows/build.yml")).read()

    check("Runner windows-latest",
          "windows-latest" in content)
    check("Python 3.11 configurado",
          "python-version" in content and "3.11" in content)
    check("Node.js 20 configurado",
          "node-version" in content and "20" in content)
    check("ffmpeg instalado (choco)",
          "choco install ffmpeg" in content)
    check("PyInstaller instalado",
          "pyinstaller" in content.lower())
    check("yt-dlp[default] instalado",
          "yt-dlp[default]" in content)
    check("--onedir no PyInstaller (não --onefile)",
          "--onedir" in content,
          "--onefile não permite executar binários externos como yt-dlp")
    check("Passo de verificação do server.exe",
          "server.exe encontrado" in content or "server/server.exe" in content)
    check("Passo de cópia python-dist/server → server/",
          "Copy-Item" in content and "server" in content)
    check("Upload do artefato configurado",
          "upload-artifact" in content)
    check("workflow_dispatch (trigger manual)",
          "workflow_dispatch" in content)


# ── Sumário ──────────────────────────────────────────────────────────────────

def summary():
    print(f"\n{'═'*52}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}✓ TODOS OS TESTES PASSARAM ({passed}/{total}){RESET}")
        print(f"{GREEN}Seguro para rodar o build.{RESET}")
    else:
        print(f"{RED}{BOLD}✗ {failed} TESTE(S) FALHARAM ({passed}/{total} passou){RESET}")
        print(f"{RED}Corrija antes de fazer build.{RESET}")
    print(f"{'═'*52}\n")
    return failed == 0


if __name__ == "__main__":
    print(f"\n{BOLD}GIOW Desktop — Suite de Testes{RESET}")
    print(f"Dir: {ROOT}")

    test_structure()
    test_syntax()
    test_package_json()
    test_main_js()
    test_preload_js()
    test_server_py()
    test_build_yml()

    ok = summary()
    sys.exit(0 if ok else 1)
