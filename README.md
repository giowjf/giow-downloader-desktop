# GIOW Downloader — Desktop

Executável portátil para Windows 10/11. Sem instalação, sem proxy, download direto do YouTube.

## Como gerar o .exe

### Opção A — GitHub Actions (recomendado)
1. Crie um repositório no GitHub com estes arquivos
2. Vá em **Actions** → **Build Windows EXE** → **Run workflow**
3. Aguarde ~5 minutos
4. Baixe o `.exe` em **Artifacts**

Para release automático, crie uma tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```
O `.exe` vai aparecer em **Releases** automaticamente.

### Opção B — Build local (Windows)
```bash
pip install "yt-dlp[default]" flask flask-cors pyinstaller
npm install
python build.py
```

## Estrutura do projeto

```
giow-desktop/
├── src/
│   ├── main.js        # processo principal Electron
│   ├── preload.js     # bridge segura front ↔ Electron
│   ├── index.html     # interface 8-bit
│   ├── script.js      # lógica do front (download local)
│   └── style.css      # estilos pixel art
├── python/
│   └── server.py      # API Flask local (analyze + download)
├── .github/workflows/
│   └── build.yml      # CI/CD para gerar o .exe
├── package.json
└── build.py           # script de build manual
```

## Como funciona

1. O `.exe` inicia o servidor Python em `localhost:5001`
2. Abre a janela Electron com a interface 8-bit
3. O `yt-dlp` (bundled) extrai os formatos do YouTube
4. O download vai **diretamente do YouTube para o disco** — sem proxy, sem throttling
5. O ffmpeg (bundled) mescla vídeo+áudio automaticamente

## Diferenças vs versão web

| | Web (downloader.giow.pro) | Desktop (.exe) |
|---|---|---|
| Analyze | ~24s (Render Free) | ~5-10s (local) |
| Download | Lento (via Worker) | Velocidade total da internet |
| Proxy | Cloudflare Worker | Nenhum |
| Offline | Não | Sim (após instalar) |
| Formatos | 1080p+ | Até 8K + mux automático |
