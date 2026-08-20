# Digimon TCG Lab

**Meta Analysis & Personal Ban List Manager**

Ferramenta desktop local-first para consultar cartas do Digimon TCG, analisar
o meta competitivo e manter sua própria Ban List pessoal — sem servidor,
sem login, sem dependência de internet para o essencial.

## Rodando em desenvolvimento

O repositório já inclui `data/cards.json` (catálogo oficial completo, ~4400
cartas) e os datasets de meta reais coletados via Limitless TCG — não é
necessário gerar nada para rodar em uma máquina nova.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Se `data/*.json` não existir por algum motivo, o app copia automaticamente
os dados de exemplo em `data/mock/` no primeiro start
(`core.paths.ensure_app_data_seeded`).

### Imagens de cartas

O app resolve a arte de cada carta em três níveis, nessa ordem:

1. `cards/` (se você empacotar imagens junto do app — opcional).
2. Uma pasta externa opcional (ex.: instalação local do Digimon Card Game
   Online). Por padrão o app procura em `~/Dcgo/Assets/Textures/Card`; para
   apontar para outro local, defina a variável de ambiente
   `DIGIMON_TCG_LAB_EXTERNAL_CARDS` antes de rodar. É seguro deixar sem
   configurar — o app cai para o próximo passo.
3. Cache local de imagens baixadas sob demanda da CDN pública do
   digimoncard.io (`core/image_cache.py`).

## Gerando o executável

```bat
build.bat
```

Gera `dist\DigimonTCGLab.exe` (build onefile via PyInstaller).

## Estrutura

- `app/` — UI (PySide6): janela principal, sidebar, páginas, componentes.
- `core/` — lógica: banco SQLite local, Ban List, Ban Score, análise de meta,
  configurações, update manager.
- `data/` — datasets compartilhados reais (`cards.json`, `decks.json`,
  `tournaments.json`, `meta.json`, `meta_entries.json`, `version.json`) e
  `data/mock/` com o gerador de dados de exemplo (fallback).
- `data_collector/` — scripts offline (rodados manualmente, fora do app) que
  regeneram os JSONs de `data/` a partir de fontes públicas
  (digimoncard.io para cartas, Limitless TCG para torneios/meta). Não fazem
  parte do `.exe` empacotado.
- Dados pessoais do usuário (Ban List, histórico, preferências) ficam em
  `%LOCALAPPDATA%\DigimonTCGLab\` — nunca no diretório do app.

## Re-coletando dados (opcional)

```bat
python data_collector\fetch_digimon_data.py
python data_collector\fetch_limitless_meta.py
```

`fetch_limitless_meta.py` usa a API pública do Limitless TCG (sem chave,
escopo travado em `game=DCG`, apenas Digimon TCG). `fetch_digilab_meta.py`
é opcional e requer uma chave de API própria (variável `DIGILAB_API_KEY` ou
um arquivo local `data_collector/digilab_key.txt`, ambos fora do controle de
versão) — não é necessário para rodar o app.

## Notas

- O app nunca faz scraping por conta própria em tempo de execução; ele
  apenas lê os JSONs estáticos em `data/`, produzidos offline pelos scripts
  de `data_collector/`.
- Ban Score é uma métrica analítica própria do Digimon TCG Lab e não é uma
  recomendação oficial da Bandai ou do DigimonMeta.
