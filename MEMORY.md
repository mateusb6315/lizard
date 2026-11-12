# Memória do LizardConverter

O nome comercial é **LizardConverter**. O build portátil para Windows x64 entrega `Lizard.exe` na pasta `lizard-converter-<versão>`. A marca anterior, Blackberry, aparece no histórico do protótipo e em artefatos locais antigos.

## Organização do código

- `main.py` inicia o PyQt6 e resolve caminhos pela raiz do projeto em desenvolvimento ou pela pasta do executável no pacote.
- `interface/componentes.py` define a janela e o tema claro. Os recursos claros estão referenciados em `interface/themes/default.py`. A paleta e os ajustes escuros ficam em `interface/themes/dark.py`.
- `interface/controlador.py` liga a interface ao serviço em uma thread de trabalho. `services/metadados.py` carrega os catálogos de `data/formatos/`. `services/conversor.py` inspeciona, planeja, executa e verifica a saída.

## Decisões do produto

- Os catálogos são lidos na inicialização e declaram candidatos à cópia. O serviço oferece ao controlador as faixas elegíveis para revisão após o FFprobe. A interface informa as omissões e limita a escolha de faixas nos formatos de áudio de faixa única. O serviço testa as cópias e valida a saída antes de disponibilizá-la em um caminho novo.
- O pacote portátil grava o tema em `data/preferences.json` no fechamento normal. Em Program Files ou em instalações reconhecidas do Inno Setup, a preferência fica em `%LOCALAPPDATA%\LizardConverter\preferences.json` e a leitura inicial pode recuperar o arquivo antigo ao lado do executável. O formato continua `{"theme": "dark"}` ou `{"theme": "default"}`.
- `docs/` e `temp/` são diretórios locais ignorados pelo Git. `README.md` e `README_en.md` são as referências públicas para uso e contribuição. O arquivo `LICENSE` da raiz contém a Licença MIT do projeto. Os componentes de terceiros seguem os termos que acompanham seus recursos e o pacote.

## Empacotamento e verificação

- `scripts/compilar.py` e `scripts/beta.py` compartilham a configuração PyInstaller e publicam em `dist/release/` e `dist/beta/`, respectivamente. A pasta final só é criada após a validação em staging. Ela contém `Lizard.exe` ao lado de `lib/`, `data/`, `tools/`, `resources/`, `license/` e `build.json`.
- `resources/lizard.ico` deriva de `resources/logo_dark.png` e é incorporado ao executável durante o build. A logo em PNG continua disponível para a interface.
- Os binários de mídia e suas DLLs ficam em `tools/ffmpeg/`. `tools/ffmpeg/ORIGEM.md` registra a origem e os hashes usados na validação do build.
- Execute `python -B -m unittest discover -s tests -v` no ambiente com PyQt6. Os testes de mídia que exigem FFmpeg e FFprobe locais são pulados quando os executáveis estão ausentes.
