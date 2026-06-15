<h1 align="center">
  Misogyny Index in Song Lyrics
</h1>

<p align="center">
  <strong>Uma análise computacional dos novos ritmos da Região Metropolitana do Recife</strong>
</p>

<p align="center">
  Dissertação de Mestrado — Centro de Informática (CIn) · UFPE
</p>

---

## Sobre

Este projeto propõe um **Índice de Misoginia (IM)** para letras de músicas dos gêneros populares da Região Metropolitana do Recife.

A metodologia é fundamentada na baseline de [Betti, Abrate e Kaltenbrunner (2023)](https://doi.org/10.1140/epjds/s13688-023-00384-8), adaptada ao português brasileiro e ao vocabulário regional de Pernambuco.

---

## Pipeline

O pipeline compreende **14 etapas** organizadas em 5 módulos:

| Etapa | Módulo | Descrição | Recurso |
|:-----:|--------|-----------|---------|
| 1 | Coleta | Coleta de músicas e letras | Spotify API + Letras.mus.br / Vagalume / Genius |
| 2 | Coleta | Filtragem básica do corpus | `langdetect` (PT-BR) |
| 3 | Coleta | Detecção e remoção de duplicatas | Jaccard em 3-gramas |
| 4 | Coleta | Enriquecimento de popularidade | Spotify `popularity` |
| 5 | Pré-proc. | Normalização, tokenização, lematização | spaCy `pt_core_news_sm` |
| 6 | Class. | Anotação e dataset de treino | AMI / OFFComBR / Codebook próprio |
| 7 | Class. | Fine-tuning do classificador | BERTimbau |
| 8 | Class. | Aplicação ao corpus; score por música | Sliding window 4 linhas |
| 9 | Viés | Extração de nomes próprios (IBGE) | API de nomes IBGE |
| 10 | Viés | Construção dos word sets WEAT em PT | WEAT1+2 traduzidos |
| 11 | Viés | Busca de hiperparâmetros Word2Vec | Gensim + WS353-PT |
| 12 | Viés | Treinamento W2V (5 seeds) + WEAT | WEAT / SC-WEAT / SWEAT |
| 13 | Índice | **Cálculo do Índice de Misoginia** | - |
| 14 | Resultados | Análise e visualização | matplotlib + seaborn |

---

## Estrutura

```
misogyny-index-recife/
│
├── data/
│   ├── raw/                  ← banco SQLite e dados brutos (não versionado)
│   ├── processed/            ← corpus filtrado e exportado (.jsonl.gz)
│   ├── lexicon/              ← léxico de gírias pernambucanas
│   └── Data_WEAT/            ← word sets para os testes WEAT
│
├── dataset_builder/          ← scripts de coleta do dataset
│   ├── 01_setup_db.py        ← cria o banco SQLite
│   ├── 02_seed_manual.py     ← popula com músicas de exemplo
│   ├── 03_collect_spotify.py ← coleta metadados do Spotify
│   ├── 04_collect_lyrics.py  ← coleta letras (Letras.mus.br / Vagalume / Genius)
│   ├── 05_export.py          ← exporta para JSON Lines / CSV
│   └── playlists.txt         ← IDs das playlists para coleta
│
├── notebooks/                ← notebooks do pipeline de análise
├── src/                      ← código reutilizável
│   └── WEAT.py               ← implementação WEAT / SC-WEAT / SWEAT
│
├── models/                   ← modelos treinados (não versionado)
├── results/                  ← resultados e visualizações
├── docs/                     ← LaTeX da dissertação e relatórios
├── baseline/                 ← submodule do repositório da baseline
│
├── .gitignore
├── README.md
└── requirements.txt
```

---

## Setup

### Pré-requisitos

- Python ≥ 3.10
- Conta no [Spotify Developer](https://developer.spotify.com/dashboard)
- Conta no [Vagalume](https://auth.vagalume.com.br) (opcional)
- Conta no [Genius](https://genius.com/api-clients) (opcional)

### Instalação

```bash
# Clonar o repositório
git clone https://github.com/biancanathally/misogyny-index-msc.git
cd misogyny-index-recife

# Criar e ativar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt
python -m spacy download pt_core_news_sm
```

### Variáveis de ambiente

Crie um arquivo `.env` (não versionado) ou exporte no terminal:

```bash
export SPOTIPY_CLIENT_ID='seu_client_id'
export SPOTIPY_CLIENT_SECRET='seu_client_secret'
export SPOTIPY_REDIRECT_URI='http://127.0.0.1:8000/callback'
# export VAGALUME_API_KEY='sua_api_key'          # opcional
# export GENIUS_ACCESS_TOKEN='seu_token'          # opcional
```

---

## Coleta

```bash
cd dataset_builder

# 1. Criar o banco de dados
python 01_setup_db.py

# 2. (Opcional) Popular com músicas de exemplo
python 02_seed_manual.py

# 3. Coletar músicas do Spotify
#    Edite playlists.txt com os IDs das playlists
python 03_collect_spotify.py --file playlists.txt

# 4. Coletar letras automaticamente
python 04_collect_lyrics.py

# 5. Verificar progresso
python 05_export.py --stats

# 6. Exportar para o formato do pipeline
python 05_export.py
```

### Banco de dados

O dataset é armazenado em SQLite (`data/raw/dataset.db`) com 4 tabelas:

```sql
artists          ← artistas (id, nome, gênero, tipo, cidade)
songs            ← músicas (id, título, artista, gênero musical, popularidade, ano)
lyrics           ← letras (texto, fonte, nº palavras, nº linhas, score de matching)
playlist_sources ← rastreabilidade (de qual playlist veio cada música)
```

A view `v_ready` retorna automaticamente as músicas prontas para o pipeline (com letra, ≥10 palavras, ≥4 linhas).

---

## Baseline

Pipeline baseado em:

> Betti, L.; Abrate, C.; Kaltenbrunner, A. (2023). **Large scale analysis of gender bias and sexism in song lyrics**. *EPJ Data Science*, 12(10).
> DOI: [10.1140/epjds/s13688-023-00384-8](https://doi.org/10.1140/epjds/s13688-023-00384-8)

Repositório original: [github.com/Loreb92/sexism_and_bias_in_song_lyrics](https://github.com/Loreb92/sexism_and_bias_in_song_lyrics)

---

**Bianca Nathally Bezerra de Lima**
Mestrado em Ciência da Computação — CIn/UFPE
[bnbl@cin.ufpe.br](mailto:bnbl@cin.ufpe.br)
