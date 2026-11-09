# ROADMAP.md — Projeto Blackberry

> **Plano provisório, não checklist de funcionalidades prontas.** O foco é **continuar os arquivos que o autor já começou**. Mudar a sequência quando os resultados dos testes ou novas decisões exigirem; registrar o motivo. Não introduzir módulos adicionais por antecipação.

## Estado inicial verificado no protótipo

- [x] Esqueleto de diretórios criado com `interface/`, `services/`, `data/formatos/`, `tools/`, `tests/`, `scripts/`, `docs/` e `changelog/`.
- [x] `data/formatos/video.json` com 17 entradas e `audio.json` com 14 entradas.
- [x] Comentários de intenção escritos em `interface/componentes.py`, `interface/textos.py`, `interface/controlador.py`, `services/formatos.py` e `services/conversor.py`.
- [x] Início de `services/formatos.py`: imports, `METADADOS` e assinatura de `carregar_formatos()`.
- [x] Início de `services/conversor.py`: importação e chamada de `carregar_formatos()`.
- [ ] Aplicação executável, integração PyQt6, conversão funcional e binários em `tools/` — **ainda não implementados**.

## Etapa 1 — Completar os blocos existentes de dados (primeira implementação)

- [x] Ler os comentários e o código existente de `services/formatos.py` e `services/conversor.py`.
- [x] Completar `carregar_formatos()` para ler os dois arquivos e devolver os catálogos nas chaves `video` e `audio`, com erros que identificam o arquivo e, quando aplicável, o campo inválido.
- [x] Preservar o esquema e os dados atuais dos catálogos.
- [x] Verificar leitura, chaves esperadas, arquivos inválidos ou ausentes e execução fora da raiz com `python -B -m unittest discover -s tests -v`.
- [x] Verificar que a chamada existente em `services/conversor.py` já recebe os dois catálogos.

**Aceite:** importar e consultar os dois catálogos funciona e tem testes reproduzíveis; o agente não substituiu os trechos iniciados pelo autor.

## Etapa 2 — Inspeção de mídia e plano de conversão

- [ ] Quando `tools/` receber os executáveis, implementar resolução dos caminhos locais do FFprobe/FFmpeg e mensagens claras se ausentes.
- [ ] Consultar o FFprobe em saída JSON para os streams selecionados; tratar arquivos inválidos e resultados incompletos.
- [ ] Implementar no próprio `services/conversor.py` uma decisão inicial explícita por stream entre copiar, recodificar ou compatibilidade indefinida.
- [ ] Utilizar as listas `copy` como candidatos, **não como autorização suficiente** para qualquer combinação de contêiner/codec.
- [ ] Definir e documentar o escopo inicial de seleção de faixas antes de codificar o mapeamento.
- [ ] Não aplicar fallback silencioso; usar parâmetros de recodificação somente após validação ou política aprovada.

**Aceite:** para entradas de teste, a decisão é explicável e testável sem alterar os dados do catálogo; nenhuma recodificação não autorizada acontece.

## Etapa 3 — Execução FFmpeg

- [ ] Completar a montagem dos argumentos e a execução no `services/conversor.py` (sem criar gerenciadores ou classes auxiliares por padrão).
- [ ] Usar `subprocess` com lista de argumentos; tratar caminhos com espaços, erro de execução, código de saída e cancelamento conforme necessidade.
- [ ] Implementar conversões mínimas de referência: remux com cópia, cópia de vídeo + áudio recodificado, vídeo recodificado + áudio copiado, áudio-only.
- [ ] Confirmar os streams gerados usando FFprobe quando possível.
- [ ] Manter tarefas demoradas fora da thread principal quando a interface for integrada.

**Aceite:** cenários representativos funcionam com mídia real e testes registram as ferramentas utilizadas; erro não é reportado como sucesso.

## Etapa 4 — Interface PyQt6 (após análise do código reutilizável)

- [ ] Receber e inspecionar o projeto de origem da interface; identificar componentes visuais que possam ser reaproveitados.
- [ ] Completar `interface/textos.py` e `interface/componentes.py` respeitando os comentários existentes.
- [ ] Completar `interface/controlador.py` **somente como intermediário**, sem regras FFmpeg.
- [ ] Implementar `main.py` como ponto de entrada simples.
- [ ] Permitir selecionar entrada/saída e perfil, iniciar operação e apresentar erros/resultado; adicionar progresso e cancelamento quando o comportamento do serviço estiver definido.
- [ ] Manter interface responsiva durante processamento.

**Aceite:** um fluxo completo pode ser operado pela interface, sem lógica de mídia embutida nos componentes visuais.

## Etapa 5 — Validar os perfis e a qualidade

- [ ] Revisar os valores `copy` dos dois JSONs com testes de muxing e inspeção; começar pelos formatos mais usados, sem tentar certificar todos ao mesmo tempo.
- [ ] Revisar especialmente: alias `h265`/`hevc`; `aac` listado para cópia em `mp3`; perfis repetidos; formatos pouco comuns; limite dos 128 kb/s em áudio multicanal.
- [ ] Testar entradas com streams múltiplos, codecs não previstos, arquivos problemáticos e filtros que impedem copy.
- [ ] Definir comportamento explícito para situações não cobertas por perfil/compatibilidade.
- [ ] Ajustar defaults de qualidade com base em resultados, não apenas em bitrate nominal.

**Aceite:** lista dos cenários suportados e das limitações documentada, com verificações executadas (e não apenas presumidas).

## Etapa 6 — Ferramentas portáteis e distribuição

- [ ] Definir SO/arquitetura de destino e política de distribuição.
- [ ] **Baixar posteriormente** FFmpeg e FFprobe em `tools/`, de fonte confiável e compatível; registrar origem, licença, versão, integridade e encoders/muxers disponíveis.
- [ ] Decidir como distribuir Python/PyQt6 e como resolver caminhos num pacote final.
- [ ] Verificar execução em ambiente limpo e revisar README e avisos de licenciamento.

**Aceite:** uma instalação de teste encontra seus recursos sem depender de FFmpeg previamente instalado no PATH.

## Questões para decisão do autor

- [ ] SO-alvo e forma de distribuição portátil.
- [ ] Perfil flexível de preservação versus perfis de codecs obrigatórios.
- [ ] Seleção de múltiplos streams de áudio, legendas, capítulos e anexos.
- [ ] Política para codec/contêiner desconhecido ou incompatibilidade ambígua.
- [ ] Qualidade padrão para recodificação, especialmente áudio multicanal.
- [ ] Quais componentes da interface antiga serão reaproveitados.

## Regra de atualização

Marque uma tarefa concluída **somente após implementar e verificar** o resultado. Registre eventuais bloqueios e os testes não executados. Não use o roadmap para impor classes, novas camadas ou recursos que não foram solicitados.
