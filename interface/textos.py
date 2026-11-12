# componentes de texto utilizados na interface do usuário

TITULO = "LizardConverter"
ABRIR = "Abrir"
SAIR = "Sair"
SALVAR = "Salvar arquivo convertido"
ARQUIVO = "Arquivo"
OPCOES = "Opções"
TEMA_CLARO = "Tema claro"
TEMA_ESCURO = "Tema escuro"
PREFERENCIAS_ERRO = "Não foi possível salvar a preferência de tema."
CATALOGOS_ERRO = "Não foi possível carregar os formatos de conversão."
ATUALIZACOES = "Procurar atualizações"
ATUALIZACOES_PENDENTES = "A busca de atualizações ficará disponível em uma versão futura."
ENTRADA = "Arraste um arquivo de mídia ou clique para abrir"
FORMATO = "Formato de saída"
CATEGORIA = "Tipo de saída"
CATEGORIAS = {"video": "Vídeo", "audio": "Áudio"}
CATEGORIA_INDISPONIVEL = "Nenhum formato disponível nesta categoria."
CONVERTER = "Converter"
AJUDA = "Faixas compatíveis são copiadas. As demais podem ser recodificadas."
FILTRO_ENTRADA = "Arquivos de mídia ({extensoes})"
FILTRO_SAIDA = "{formato} (*.{extensao})"
ENTRADA_INVALIDA = "Não foi possível abrir o arquivo selecionado."
SAIDA_INVALIDA = "Não foi possível usar o destino selecionado."
FERRAMENTA_AUSENTE = "Não foi possível iniciar a conversão."
SUCESSO = "Conversão concluída.\n{saida}"
ERRO = "Não foi possível concluir a conversão."
AVISO_RECODIFICACAO = "Foi necessário recodificar uma ou mais faixas."
AVISO_INICIO_TS = "O vídeo convertido começa no primeiro quadro recuperável."
AVISO_FIM_TS = (
    "A recuperação automática removeu cerca de {perda} s do fim do MPEG-TS. "
    "O arquivo convertido pode apresentar falhas de reprodução devido à compatibilidade limitada "
    "entre MPEG-TS e o formato escolhido."
)
CANCELADO = "Conversão cancelada."
PROGRESSO = "Conversão em andamento"
TEMPO = "Tempo decorrido {tempo}"
CANCELAR = "Cancelar"
CANCELANDO = "Cancelando conversão…"
FAIXAS = "Faixas de saída"
SELECIONAR_FAIXAS = "Escolha as faixas que deseja incluir em {formato}."
FAIXA_UNICA = "Este formato aceita apenas uma faixa de áudio. Para preservar várias, escolha um formato como MKA."
FAIXAS_OMITIDAS = "A saída não incluirá: {tipos}."
TIPOS_OMITIDOS = {
    "subtitle": "legendas",
    "attachment": "anexos",
    "capa": "capas",
    "data": "faixas de dados",
}
OUTRAS_FAIXAS = "outras faixas"
CONTINUAR = "Continuar"
ETAPAS = {
    "inspecao": "Inspecionando o arquivo…",
    "planejamento": "Verificando compatibilidade…",
    "conversao": "Convertendo o arquivo…",
    "validacao": "Verificando a saída…",
}
