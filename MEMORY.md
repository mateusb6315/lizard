# Memória do LizardConverter

O nome comercial é **LizardConverter**. O build portátil para Windows x64 entrega a pasta `LizardConverter` e o executável `Lizard.exe`. A marca anterior, Blackberry, aparece no histórico do protótipo e em artefatos locais antigos.

## Organização do código

- `main.py` inicia o PyQt6 e resolve caminhos pela raiz do projeto em desenvolvimento ou pela pasta do executável no pacote.
- `interface/componentes.py` define a janela e o tema claro. Os recursos claros estão referenciados em `interface/themes/default.py`. A paleta e os ajustes escuros ficam em `interface/themes/dark.py`.
- `interface/controlador.py` liga a interface ao serviço em uma thread de trabalho. `services/metadados.py` carrega os catálogos de `data/formatos/`. `services/conversor.py` inspeciona, planeja, executa e verifica a saída.

## Decisões do produto

- Os catálogos declaram candidatos à cópia. A seleção automática separa áudio de vídeo e exclui capas anexadas. O serviço usa FFprobe e verifica as tentativas de cópia no formato de destino. A saída é validada antes da publicação em um caminho novo.
- A persistência de tema está ativa no pacote compilado. No fechamento normal, `data/preferences.json` recebe `{"theme": "dark"}` ou `{"theme": "default"}`. A ausência ou invalidade do arquivo resulta no tema claro.
- `docs/` e `temp/` são diretórios locais ignorados pelo Git. `README.md` e `README_en.md` são as referências públicas para uso e contribuição. O arquivo `LICENSE` da raiz contém a Licença MIT do projeto. Os componentes de terceiros seguem os termos que acompanham seus recursos e o pacote.

## Empacotamento e verificação

- `scripts/compilar.py` e `scripts/beta.py` compartilham a configuração PyInstaller. A estrutura do pacote é `Lizard.exe` ao lado de `lib/`, `data/`, `tools/`, `resources/`, `license/` e `build.json`.
- `resources/lizard.ico` deriva de `resources/logo_dark.png` e é incorporado ao executável durante o build. A logo em PNG continua disponível para a interface.
- Os binários de mídia e suas DLLs ficam em `tools/ffmpeg/`. `tools/ffmpeg/ORIGEM.md` registra a origem e os hashes usados na validação do build.
- Execute `python -B -m unittest discover -s tests -v` no ambiente com PyQt6. Os testes de mídia que exigem FFmpeg e FFprobe locais são pulados quando os executáveis estão ausentes.
