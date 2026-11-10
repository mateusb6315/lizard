# AGENTS.md — LizardConverter

> Instruções para agentes de desenvolvimento. O repositório e seus comentários são a fonte primária para compreender o estado atual. Consulte `MEMORY.md` para decisões do projeto e os documentos locais em `docs/` quando estiverem disponíveis.

## 1. Prioridade absoluta: continuar o protótipo existente

- **Inspecione a árvore e leia os arquivos pertinentes antes de editar.** Não recrie o projeto do zero nem substitua trechos existentes por uma arquitetura própria.
- **Preserve os nomes e caminhos atuais** (`services/`, `tools/`, `interface/controlador.py`, etc.). Não restaure nomes antigos como `servicos/` ou `vendor/`.
- **Leia e respeite os comentários no início dos módulos**: são indicações deliberadas do autor sobre sua responsabilidade. Caso um comentário esteja ambíguo ou conflite com o comportamento real, explique a diferença; não o ignore silenciosamente.
- Continue os pequenos blocos de código escritos pelo autor. Prefira completar a implementação iniciada a criar arquivos ou classes substitutos.
- Preserve a intenção dos catálogos existentes em `data/formatos/`; não reformate, renomeie chaves, agrupe extensões ou altere codecs e parâmetros incidentalmente.
- Não declare funcionalidades implementadas apenas porque estão previstas na documentação.

## 2. Princípios de desenvolvimento

- **KISS, legibilidade, eficiência, SRP e baixo acoplamento**, aplicados pragmaticamente; padrões como MVC servem de inspiração, não de obrigação formal.
- Evite complexidade acidental: interfaces abstratas, factories, managers, adapters, containers de dependências, camadas de serviço adicionais e hierarquias de classes sem motivo concreto.
- Prefira funções pequenas, nomes claros e fluxo explícito. Use classes quando houver estado/vida útil de objetos que as justifique (por exemplo, widgets Qt), não como padrão obrigatório.
- Não fragmente módulos por contagem de linhas. Divida responsabilidades somente diante de problemas concretos de coesão, testes ou manutenção.
- Não realize refatorações preventivas ou alterações fora do escopo. Se encontrar problemas adjacentes, registre-os para decisão posterior.
- Não adicione dependências, recursos de interface ou configurações sem necessidade demonstrada e autorização pertinente.

## 3. Limites dos módulos atuais

- `interface/componentes.py`: componentes visuais da interface PyQt6.
- `interface/textos.py`: textos utilizados na interface.
- `interface/controlador.py`: intermediário entre eventos/componentes visuais e serviços, conforme seu comentário de SRP; não processa mídia nem monta comandos FFmpeg.
- `services/metadados.py`: carrega e disponibiliza os JSONs de `data/formatos/`; não decide copy/transcode nem executa FFmpeg.
- `services/conversor.py`: inspeciona os arquivos (FFprobe), determina a estratégia permitida, monta argumentos e executa FFmpeg. Não contém widgets Qt.
- `data/formatos/video.json` e `audio.json`: catálogos declarativos existentes; são dados/propostas de compatibilidade, **não garantias técnicas**.
- `tools/`: destino de FFmpeg e FFprobe portáteis. Verifique a presença e a procedência dos executáveis.
- `main.py`: ponto de entrada da interface. `tests/` contém as verificações e `scripts/` contém o empacotamento para Windows.

## 4. Regras de qualidade de mídia

- Priorize **preservação sem recodificação quando for válida**; não confunda extensão do arquivo, contêiner, codec e encoder.
- Inspecione streams com FFprobe antes de planejar uma conversão; verifique codec, tipo e características relevantes.
- Trate vídeo e áudio independentemente; filtros ou alterações de codec/qualidade geralmente exigem recodificação daquele stream.
- Uma entrada em `copy` dos JSONs indica apenas **candidato** à cópia. Verifique suporte no muxer/perfil, restrições reais e seleção dos streams. Não suponha que o FFmpeg possa copiar com base só no nome do codec.
- Defina o mapeamento dos streams explicitamente; não confie em seleção automática para preservar todas as faixas.
- Não use `shell=True` para executar FFmpeg/FFprobe; forneça uma lista de argumentos ao subprocesso. Cuide de caminhos com espaços e da saída sem sobrescrever a entrada.
- **Não recodifique silenciosamente como fallback** depois de falha no `copy`. Informe o erro e a alternativa, ou siga uma política explicitamente aprovada.
- Não imponha 128 kb/s para qualquer áudio sem avaliar o caso, especialmente multicanal. Preservar bitrate não equivale a preservar qualidade.
- Trate falhas de execução, códigos de saída e diagnósticos; valide o resultado conforme o cenário e jamais reporte sucesso antes da conclusão do processo.

## 5. Trabalho com os catálogos

- Preserve o esquema atual por padrão: entradas por nome de formato; `extension`; blocos `video`/`audio`; campos `copy`, `encode` (atualmente **listas**) e `args` quando aplicável.
- Reutilize `carregar_formatos()` em `services/metadados.py`. Use `json` e `pathlib` da biblioteca padrão e trate arquivos ausentes e JSON malformado de maneira compreensível.
- Qualquer correção de codec, alias, parâmetro ou regra de compatibilidade deve ser **explícita, localizada e testada**, não uma reescrita generalizada. Registre mudanças que alterem o comportamento de saída.
- Se uma decisão estiver indefinida (múltiplos áudios, legendas, perfis, presets), implemente apenas o escopo acordado e documente os limites.

## 6. Fluxo mínimo para cada tarefa

1. Ler a tarefa, os arquivos afetados, seus comentários e `MEMORY.md`. Conferir as seções relevantes de `docs/ARCHITECTURE.md` e `docs/ROADMAP.md` quando esses arquivos locais estiverem disponíveis.
2. Identificar o que já existe, o que está incompleto e o que de fato precisa mudar.
3. Para alterações maiores, apresentar um plano curto; não ampliar escopo por iniciativa própria.
4. Implementar a **menor alteração coerente**. Não apagar nem reformatar código sem motivo.
5. Executar verificações proporcionais: sintaxe/imports, leitura dos JSONs, testes automatizados e/ou mídia de amostra, quando houver FFmpeg disponível.
6. Relatar: arquivos alterados, comportamento implementado, testes realmente executados, limitações, decisões pendentes e qualquer ação necessária do autor.
7. Atualizar o roadmap apenas quando houver avanço real; registrar mudança arquitetural relevante em `ARCHITECTURE.md` sem apresentá-la como definitiva se ainda estiver em avaliação.

## 7. Dependências e binários

- O protótipo usa Python, PyQt6 e executáveis **FFmpeg/FFprobe locais** em `tools/`; o ambiente-alvo e o empacotamento final ainda não estão definidos.
- `tools/ORIGEM.md` registra a build de Windows x64 usada no empacotamento e os hashes esperados. Em uma substituição autorizada, verificar licença, procedência, integridade, versão e encoders disponíveis e atualizar o registro.
- Não criar testes que dependam dos binários sem possibilidade de pular/assinalar a ausência deles de maneira clara.

## 8. Autoridade das informações

Em caso de conflito: **instrução atual do autor > código e comentários atuais do repositório > decisões registradas em `docs/ARCHITECTURE.md` > plano em `docs/ROADMAP.md` > sugestões anteriores**. Informe conflitos relevantes antes de fazer alterações destrutivas. Não trate os arquivos Markdown como especificação imutável.
