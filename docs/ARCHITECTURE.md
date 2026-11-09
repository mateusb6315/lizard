# ARCHITECTURE.md — Projeto Blackberry

**Estado:** especificação provisória do protótipo, baseada no esqueleto fornecido. **Não descreve um aplicativo pronto.**

**Objetivo:** conversor desktop de mídia em Python, com interface PyQt6 e FFmpeg/FFprobe distribuídos localmente na pasta `tools/` em etapa posterior.

## 1. Intenção e filosofia

O Blackberry deve converter/remuxar arquivos de mídia de maneira compreensível, priorizando a qualidade do conteúdo original. Sua arquitetura foi inspirada em MVC, SRP, Clean Code e baixo acoplamento, **sem compromisso com padrões formais ou camadas extras**. Busca-se minimizar a dificuldade de manutenção — especialmente ao trabalhar com agentes de IA — preservando código explícito e responsabilidades identificáveis.

**Princípio orientador:** a menor estrutura que atenda corretamente aos casos de uso, com espaço para evoluir quando os requisitos forem confirmados.

## 2. Árvore observada no ZIP

```text
blackberry/
├── AGENTS.md                    # arquivo vazio no protótipo original
├── LICENSE                      # vazio
├── README.md                    # vazio
├── main.py                      # vazio
├── interface/
│   ├── componentes.py           # comentário de propósito
│   ├── controlador.py           # comentário de SRP
│   └── textos.py                # comentário de propósito
├── services/
│   ├── conversor.py             # import e chamada de carregar_formatos()
│   └── formatos.py              # início do leitor JSON, ainda incompleto
├── data/
│   └── formatos/
│       ├── video.json           # 17 entradas
│       └── audio.json           # 14 entradas
├── tools/                       # vazio; receberá FFmpeg e FFprobe
├── tests/                       # vazio
├── scripts/                     # vazio
├── docs/
│   ├── ARCHITECTURE.md          # vazio no protótipo original
│   └── ROADMAP.md               # vazio no protótipo original
└── changelog/                   # vazio
```

Essa árvore tem prioridade sobre rascunhos anteriores: `services` substituiu `servicos`, `tools` substituiu `vendor` e o arquivo atual é `interface/controlador.py` (singular). Não criar `lib/` ou `controladores.py` porque constavam em desenhos anteriores.

## 3. Responsabilidades existentes e previstas

| Elemento | Papel | Situação no ZIP |
|---|---|---|
| `main.py` | Ponto de entrada e inicialização da aplicação PyQt6 | Vazio |
| `interface/componentes.py` | Componentes gráficos | Somente comentário |
| `interface/textos.py` | Textos da interface | Somente comentário |
| `interface/controlador.py` | Intermediar interface e serviços; comentário original enfatiza SRP | Somente comentário |
| `services/formatos.py` | Ler e disponibilizar metadados dos formatos | `METADADOS` e `carregar_formatos()` iniciados; função incompleta |
| `services/conversor.py` | Lógica de conversão: copiar ou recodificar, auxiliada por FFprobe e metadados | Importa e chama `carregar_formatos()`; ainda sem conversão |
| `data/formatos/*.json` | Definições declarativas de formatos | Populados, compatibilidade não validada integralmente |
| `tools/` | Binários locais FFmpeg/FFprobe | Vazios; download futuro |
| `tests/`, `scripts/`, `changelog/` | Espaços para testes, tarefas auxiliares e histórico | Vazios |

Os comentários já escritos pelo autor são parte da especificação de intenção. **Priorize completar esses arquivos** em vez de criar serviços alternativos.

## 4. Fluxo operacional proposto — ainda não implementado

```text
Usuário
  → interface/componentes.py
  → interface/controlador.py
  → services/conversor.py
      ├→ services/formatos.py → data/formatos/{video,audio}.json
      ├→ tools/ffprobe → metadados de entrada
      └→ tools/ffmpeg  → cópia/transcodificação
  → retorno do resultado/progresso ao controlador → interface
```

O controlador da interface coordena ações e apresenta resultados; **não** existe controlador na camada `services/`. A execução de processos e análise de mídia permanecem fora dos widgets. Uma interface Qt deve permanecer responsiva durante conversões longas; a técnica de execução assíncrona será escolhida quando a interface for integrada, sem impor agora um framework adicional.

## 5. Contrato dos catálogos atual

Os arquivos JSON já existem. O formato observado é:

```json
{
  "mp4": {
    "extension": "mp4",
    "video": {"copy": ["h264", "hevc"], "encode": ["libx264"]},
    "audio": {"copy": ["aac"], "encode": ["aac"], "args": ["-b:a", "128k"]}
  }
}
```

*Trecho reduzido apenas para ilustrar o esquema; não substitui a entrada real e não certifica compatibilidade.*

- `video.json`: 17 chaves de formatos/saídas com blocos `video` e `audio`.
- `audio.json`: 14 chaves com bloco `audio`.
- `extension`: extensão nominal de saída.
- `copy`: lista de **codecs candidatos** à preservação; não representa compatibilidade universal.
- `encode`: **lista** de encoders alternativos no esquema atual (na maioria dos perfis contém um item). Não mudar para string sem decisão coordenada.
- `args`: argumentos adicionais definidos no perfil; podem estar ausentes em vídeo.

Ainda não há campo `muxer`, `extensions` ou sistema de presets. Ideias anteriores de agrupamento ou migração de esquema **não foram aplicadas ao protótipo**. Não introduzi-las incidentalmente. `services/formatos.py` deve carregar e entregar esses dados; não acrescentar regras de decisão ao leitor.

## 6. Política de preservação automática — direção provisória

Objetivo: **evitar perdas geracionais e trabalho computacional desnecessário**, copiando streams quando realmente possível, e recodificando somente quando exigido pelo perfil, por transformações solicitadas ou por incompatibilidade.

Para cada stream selecionado:

1. Inspecionar a entrada com FFprobe; identificar os streams e suas características relevantes.
2. Obter o perfil de destino com `services/formatos.py`.
3. Avaliar a compatibilidade do codec e características do stream com o contêiner/muxer e a política do perfil; considerar filtros, transformações e exigências da saída.
4. Se a cópia for comprovadamente elegível, usar `-c:v copy` ou `-c:a copy` para o stream apropriado; caso haja necessidade de recodificar, escolher o encoder/args previstos para a saída.
5. Planejar a seleção/mapeamento das faixas; construir o comando como lista de argumentos e executar o FFmpeg local.
6. Comunicar falhas e validar ao menos os resultados essenciais. Não aplicar fallback de recodificação silenciosa.

**Estados conceituais:** `copiar`, `recodificar`, `indefinido`. São resultados de decisão, não classes ou enumerações obrigatórias.

### Atenções identificadas nos JSONs

- `h265` e `hevc` aparecem como entradas distintas no catálogo de MP4; conferir os identificadores efetivamente retornados pelo FFprobe.
- A entrada de `mp3` no catálogo de áudio inclui `aac` em `copy`: essa compatibilidade não deve ser aceita sem revisão específica.
- Existem perfis repetidos (por exemplo `mpeg`/`mpg`, `wmv`/`asf`, `ts`/`mts`/`m2ts`); **não consolidar cegamente**: extensões parecidas podem ter diferenças de muxing.
- Muitos perfis de vídeo definem `-b:a 128k` como fallback; essa política pode degradar áudio multicanal e precisa de avaliação antes de uso generalizado.
- Alguns encoders, contêineres e codecs podem não estar presentes na build portátil selecionada. Verificar por testes reais, não por inferência a partir do nome.

O projeto **ainda não decidiu**: quantas faixas preservar por padrão, suporte a legendas/anexos/capítulos, o que fazer com compatibilidade incerta, presets de qualidade ou perfis de dispositivo. Registre essas lacunas em vez de criar regras implícitas.

## 7. Distribuição e dependências

- FFmpeg e FFprobe estarão em `tools/` e **ainda não foram baixados**.
- O carregador deve localizar os dados a partir da estrutura do projeto, não do diretório corrente do terminal.
- A descoberta dos binários deve considerar o sistema operacional e o empacotamento escolhido; não definir nomes de `.exe` em código multiplataforma antes da decisão de alvo.
- Uma distribuição realmente portátil também precisará definir empacotamento de Python/PyQt6 e licenças dos executáveis; **não está resolvida**.
- Preferir subprocessos com lista de argumentos, sem shell, e tratamento adequado de erros e interrupções.

## 8. Interface reutilizada de outro projeto

Existe a intenção de aproveitar a interface PyQt6 de outro projeto com arquitetura diferente. O código dessa interface **não está no ZIP recebido**. Antes de portar componentes, analisar seus vínculos e reaproveitar elementos visuais úteis sem transportar serviços/controladores que conflitem com as responsabilidades do Blackberry.

## 9. Decisões e questões em aberto

**Decisões refletidas no repositório:** nomes atuais dos diretórios; dois JSONs com o esquema atual; `services/formatos.py` como leitor; `services/conversor.py` como motor; somente controlador da interface; ferramentas locais previstas em `tools/`.

**Diretrizes a validar:** preservar streams elegíveis de forma conservadora; separar decisões de vídeo/áudio; evitar recodificações silenciosas; testar compatibilidades do catálogo.

**Pendências:** plataforma-alvo, binários, integração da interface, seleção de streams, qualidade de fallback, testes de mídia reais, empacotamento e revisão dos perfis.

Toda mudança significativa deve ser justificada pelo caso de uso e refletida neste documento, respeitando o caráter provisório do projeto.