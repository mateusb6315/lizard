# AGENTS.md — LizardConverter

O LizardConverter é um conversor desktop local de áudio e vídeo para Windows x64. A interface usa PyQt6 e o pacote portátil abre por `Lizard.exe`, com FFmpeg e FFprobe incluídos.

## 1. Fontes e continuidade

- Siga a instrução atual do autor e as regras deste guia. Consulte `MEMORY.md` para decisões anteriores. Quando disponíveis, leia `docs/ARCHITECTURE.md` para os contratos e as fronteiras do aplicativo e `docs/ROADMAP.md` para o planejamento. `docs/` é local e ignorado pelo Git.
- Use a árvore, o código e os comentários de responsabilidade para verificar o comportamento existente. Se o código divergir da arquitetura ou de um comentário, registre a discrepância e confira a decisão vigente antes de tratar o comportamento como contrato. Considere propostas do roadmap como trabalho futuro até que sejam implementadas e verificadas.
- Inspecione o diff, preserve as edições locais e continue a implementação iniciada nos módulos existentes. Mantenha os nomes e os caminhos atuais, em especial `services/`, `tools/` e `interface/controlador.py`.

## 2. Regra obrigatória de projeto

**Antes de planejar qualquer função ou recurso e sempre que o escopo mudar, releia este guia e a arquitetura local, quando disponível.** Identifique o módulo responsável, as regras afetadas e a menor alteração que resolva o caso.

- Aplique KISS, SRP, legibilidade, eficiência e baixo acoplamento. Use funções de fluxo explícito e classes quando houver estado ou ciclo de vida que as justifique, como os widgets Qt.
- Crie um ponto de entrada ou helper somente para resolver uma necessidade concreta de coesão, reutilização ou teste. Registre o motivo na revisão. Preserve contratos e comentários de responsabilidade dos módulos.
- Evite refatorações preventivas, reorganização por contagem de linhas e abstrações antecipadas. Registre problemas adjacentes para decisão posterior. Mudanças de dependência, interface ou configuração exigem necessidade demonstrada e autorização pertinente.

## 3. Fronteiras dos módulos

| Módulo | Responsabilidade |
| --- | --- |
| `main.py` | Inicializar Qt, resolver a raiz de execução, fornecer caminhos e dados aos serviços, compor janela e controlador e ligar os eventos de preferências. Apresentar falhas de inicialização. |
| `interface/componentes.py`, `interface/textos.py`, `interface/themes/` | Widgets, diálogos, textos e temas. |
| `interface/controlador.py` | Intermediar a interface e o serviço de conversão, encaminhar ações e seleção, coordenar a thread de trabalho e apresentar resultados. Comandos de mídia e persistência pertencem aos serviços. |
| `services/metadados.py` | Ler e validar os JSONs dos catálogos e disponibilizá-los por `carregar_formatos()`. |
| `services/conversor.py` | Inspecionar a mídia com FFprobe, planejar a estratégia por faixa, executar FFmpeg e validar e publicar o resultado. |
| `services/logger.py` | Configurar o log local, resolver os caminhos de preferências e ler e gravar a preferência de tema. Usa a biblioteca padrão e recebe a base de dados da aplicação como caminho. |

## 4. Regras de mídia e dados

- Inspecione as faixas antes de decidir a conversão. Distinga extensão, contêiner, codec e encoder. Avalie vídeo e áudio separadamente. Priorize a cópia quando o perfil e o muxer a aceitarem e o caso preservar as características das faixas.
- Use os índices do FFprobe para seleção e mapeamento explícitos. Perfis de vídeo exigem uma faixa de vídeo real. Respeite os limites dos formatos de áudio de faixa única e informe as omissões na seleção automática.
- Preserve os catálogos em `data/formatos/`. As entradas têm `extension`, blocos `video` e/ou `audio`, listas `copy` e `encode` e `args` quando aplicável. `copy` indica um candidato a verificar no destino. Mantenha revisões de aliases, parâmetros, encoders e compatibilidade localizadas, explícitas e testadas. A política de qualidade por perfil continua em aberto, especialmente para áudio multicanal.
- Diferencie rejeição do muxer, falha de leitura ou gravação e erro de decodificação. Recodifique após uma rejeição de cópia confirmada somente para a faixa identificada, com aviso. Encerre em caso de diagnóstico ambíguo. A tolerância a SPS/PPS no início de MPEG-TS exige H.264 utilizável. A recuperação automática de LATM no fim de MPEG-TS exige confirmação da posição, admite uma nova tentativa com perda estimada de até 1 s, preserva o áudio válido do início e avisa sobre o corte após validar o resultado.
- Execute os binários locais com listas de argumentos e limite a entrada ao protocolo `file`. Preserve caminhos com espaços e o arquivo original. Encerre o subprocesso ativo ao cancelar e limpe os temporários em falhas e cancelamentos.
- Confira as faixas, codecs, canais e durações aplicáveis antes de publicar em um caminho novo. A saída com recuperação LATM exige validação de tempos e decodificação integral de vídeo e áudio. Reporte sucesso somente após a publicação. Consulte a arquitetura local para os detalhes desses contratos.

## 5. Ambiente e distribuição

- Use Python 3.13 ou superior no ambiente ativo que contenha PyQt6. Em instalações com pyenv ou ambiente virtual, confirme o interpretador efetivo antes de testar.
- FFmpeg e FFprobe para Windows x64 ficam com suas DLLs em `tools/ffmpeg/`. Confira a presença e o registro de origem e hashes em `tools/ffmpeg/ORIGEM.md`. Em substituição autorizada, valide procedência, integridade, versão, licença e encoders antes de atualizar o registro.
- O empacotamento usa PyInstaller, com `scripts/beta.py` e `scripts/compilar.py` para os canais beta e release. ZIP automatizado, instalador e publicação automatizada seguem no planejamento de distribuição.

## 6. Fluxo de trabalho e verificação

1. Leia o pedido, os arquivos afetados e seus comentários, `MEMORY.md` e a documentação local disponível. Inspecione o estado do Git e identifique o que já funciona e o que precisa mudar.
2. Aplique a regra 2, reproduza o problema quando possível e apresente um plano curto para mudanças maiores. Faça a menor alteração coerente com os contratos e as decisões vigentes.
3. Para mudanças no aplicativo, execute `python -B -m unittest discover -s tests -v` no ambiente preparado. Use FFmpeg e FFprobe reais nas regressões de mídia aplicáveis. Os testes que dependem desses executáveis devem indicar sua ausência claramente.
4. Para mudanças na inicialização, nos recursos, nos caminhos ou nas dependências, valide também a abertura e o fechamento do pacote Windows. Revise o diff e relate os arquivos alterados, o comportamento verificado, os testes aprovados ou falhos, o que ficou pendente e as decisões que ainda cabem ao autor.
5. Atualize a arquitetura quando houver mudança de contrato ou fronteira, a memória para registrar decisões e o roadmap quando houver avanço verificado. Preserve a distinção entre comportamento atual e trabalho futuro.
