# Horizonte Verde — montagem da reportagem

## Como usar
1. Coloque os clipes em `clipes/` (MP4, H.264, áudio AAC; qualquer resolução).
2. Copie `roteiro_modelo.json` para `meu_roteiro.json` e preencha os segmentos **na ordem em que devem aparecer**.
3. Rode: `python3 build.py meu_roteiro.json`
4. O resultado sai em `saida/` (1920×1080, 30 fps, H.264, áudio -16 LUFS).

## Segmentos
| tipo | o que faz |
|---|---|
| `abertura` | Abertura de 6 s no estilo jornal de TV, com o nome "Horizonte Verde". |
| `apresentador` | Clipe com legenda de nome/função no canto inferior esquerdo. |
| `reporter` | Transição: mapa do Brasil, zoom até a cidade, transição circular, depois o clipe com legenda (nome, função e cidade). |

## Animações sincronizadas com a fala (`eventos`)
Cada evento começa em `tempo` (segundos a partir do início do clipe) e dura `duracao` segundos.

- `estatistica`: painel grande à esquerda, com `valor` (ex.: "US$ 5,5 bi") e `rotulo`.
- `lista`: painel à direita, com `titulo` e `itens` que aparecem um a um.
- `manchete`: faixa inferior, com `texto` em destaque.

## Áudio
Cada clipe passa por: filtro passa-alta (corta ronco e vento graves), filtro de ruído, compressão de voz e normalização para -16 LUFS. A abertura e a transição têm vinheta e sopro próprios.

## Cidades disponíveis
Belém, Manaus, Brasília, Salvador, Recife, Fortaleza, Rio de Janeiro, São Paulo, Curitiba, Porto Alegre. Para outra cidade, informe `"lon"` e `"lat"` no segmento.

## Teste
`python3 build.py teste/projeto_teste.json` usa clipes de teste (cores e tom simulado) e gera `saida/teste_horizonte_verde.mp4`.
