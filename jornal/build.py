#!/usr/bin/env python3
"""Monta a reportagem 'Horizonte Verde' a partir de um roteiro (project.json).

Ordem típica:
  abertura (6 s, estilo jornal de TV)
  -> apresentador (clipe, legenda com nome)
  -> repórter: transição com mapa do Brasil + zoom na cidade -> clipe do repórter
  -> ... (quantos segmentos forem necessários)

Em cada clipe:
  - áudio: filtro de voz (passa-alta, redução de ruído, compressão) + loudnorm -16 LUFS
  - legenda de nome/função (repórter/apresentador)
  - animações de destaque, em horários "tempo" (segundos a partir do início do clipe)

Uso:  python3 build.py project.json
"""
import json
import os
import re
import shutil
import subprocess
import sys
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.join(HERE, 'studio.html')
RENDER_JS = os.path.join(HERE, 'render.js')
OBRA = os.path.join(HERE, 'obra')
FPS = 30
SR = 48000
DUR_ABERTURA = 6.0
DUR_MAPA = 3.0
DUR_LEGENDA = 7.0
TRANSICAO_MAPA = 0.8

# Coordenadas aproximadas (lon, lat, rótulo) de cidades usadas no mapa.
CIDADES = {
    'Belém': (-48.48, -1.46, 'Belém – PA'),
    'Manaus': (-60.02, -3.12, 'Manaus – AM'),
    'Brasília': (-47.93, -15.78, 'Brasília – DF'),
    'Salvador': (-38.50, -12.97, 'Salvador – BA'),
    'Recife': (-34.88, -8.05, 'Recife – PE'),
    'Fortaleza': (-38.54, -3.73, 'Fortaleza – CE'),
    'Rio de Janeiro': (-43.17, -22.91, 'Rio de Janeiro – RJ'),
    'São Paulo': (-46.63, -23.55, 'São Paulo – SP'),
    'Curitiba': (-49.27, -25.43, 'Curitiba – PR'),
    'Porto Alegre': (-51.23, -30.03, 'Porto Alegre – RS'),
}


def sh(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-3000:])
        raise SystemExit('Erro ao executar: ' + ' '.join(cmd[:3]) + ' ...')
    return p


def duracao(path):
    return float(sh(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'csv=p=0', path]).stdout.strip())


# ---------------- quadros e vídeo ----------------
def quadros(cfg, dur, transparente, pasta):
    os.makedirs(pasta, exist_ok=True)
    cfg_path = os.path.join(pasta, 'cfg.json')
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(dict(cfg, dur=dur), f, ensure_ascii=False)
    sh(['node', RENDER_JS, STUDIO, cfg_path, pasta, str(FPS), str(dur), '1' if transparente else '0'])


def para_webm_alfa(pasta, saida):
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{pasta}/f_%04d.png',
        '-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '0', '-crf', '32',
        '-deadline', 'realtime', '-cpu-used', '6', saida])
    shutil.rmtree(pasta, ignore_errors=True)


def para_mp4(pasta, saida):
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', f'{pasta}/f_%04d.png',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-pix_fmt', 'yuv420p', '-an', saida])
    shutil.rmtree(pasta, ignore_errors=True)


# ---------------- áudio sintetizado (abertura e transição) ----------------
def escreve_wav(caminho, y):
    pico = np.max(np.abs(y)) or 1.0
    y = np.clip(y / pico * 0.5, -1, 1)
    dados = (y * 32767).astype('<i2')
    with wave.open(caminho, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(dados.tobytes())


def gera_vinheta(dur, caminho):
    """Vinheta musical curta: arpejo de dó maior e acorde final."""
    n = int(dur * SR)
    y = np.zeros((n, 2))

    def nota(freq, t0, d, amp):
        i0, m = int(t0 * SR), int(d * SR)
        tt = np.arange(m) / SR
        env = np.minimum(1, tt / 0.02) * np.exp(-tt * 1.6)
        s = amp * (np.sin(2 * np.pi * freq * tt) + 0.3 * np.sin(4 * np.pi * freq * tt)) * env
        y[i0:i0 + m, 0] += s
        y[i0:i0 + m, 1] += s

    for k, f in enumerate([523.25, 659.25, 783.99, 1046.5]):
        nota(f, 0.3 + 0.15 * k, 0.9, 0.5)
    for f in [261.63, 329.63, 392.0, 523.25]:
        nota(f, 1.5, 4.0, 0.3)
    escreve_wav(caminho, y)


def gera_whoosh(dur, inicio, comp, caminho):
    """Sopro de transição (ruído suavizado com envelope)."""
    n = int(dur * SR)
    rng = np.random.default_rng(7)
    ruido = np.convolve(rng.standard_normal(n), np.ones(240) / 240, mode='same')
    env = np.zeros(n)
    i0, m = int(inicio * SR), int(comp * SR)
    env[i0:i0 + m] = np.sin(np.pi * np.linspace(0, 1, m)) ** 2
    y = ruido * env
    y = y / (np.max(np.abs(y)) or 1) * 0.25
    escreve_wav(caminho, np.stack([y, y], axis=1))


# ---------------- finalização (formato único em todos os segmentos) ----------------
def finaliza(src, saida, entrada=True, saida_fade=True):
    d = duracao(src)
    vf = ['fps=30', 'format=yuv420p']
    af = ['aresample=48000', 'aformat=channel_layouts=stereo']
    if entrada:
        vf.append('fade=t=in:st=0:d=0.4')
        af.append('afade=t=in:st=0:d=0.4')
    if saida_fade:
        vf.append(f'fade=t=out:st={d - 0.4:.3f}:d=0.4')
        af.append(f'afade=t=out:st={d - 0.4:.3f}:d=0.4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', src,
        '-vf', ','.join(vf), '-af', ','.join(af),
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30',
        '-s', '1920x1080', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2',
        '-movflags', '+faststart', saida])


# ---------------- segmentos ----------------
def abertura(saida):
    pasta = os.path.join(OBRA, 'abertura_frames')
    quadros({'mode': 'intro'}, DUR_ABERTURA, False, pasta)
    video = os.path.join(OBRA, 'abertura_v.mp4')
    para_mp4(pasta, video)
    vinheta = os.path.join(OBRA, 'vinheta.wav')
    gera_vinheta(DUR_ABERTURA, vinheta)
    mix = os.path.join(OBRA, 'abertura_av.mp4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', video, '-i', vinheta,
        '-filter_complex', '[1:a]loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000[a]',
        '-map', '0:v', '-map', '[a]', '-c:v', 'copy', '-c:a', 'aac', '-shortest', mix])
    finaliza(mix, saida, entrada=False, saida_fade=True)
    return saida


def info_cidade(seg):
    if 'lon' in seg and 'lat' in seg:
        return seg['lon'], seg['lat'], seg.get('cidade', '')
    nome = seg['cidade']
    if nome not in CIDADES:
        raise SystemExit(f'Cidade desconhecida "{nome}". Informe "lon" e "lat" no roteiro.')
    lon, lat, rotulo = CIDADES[nome]
    return lon, lat, rotulo


def processa_clipe(seg, idx, saida_clipe):
    """Aplica áudio tratado e animações ao clipe; devolve o caminho do clipe pronto (sem fade)."""
    clipe = seg['clipe']
    if not os.path.exists(clipe):
        raise SystemExit(f'Clipe não encontrado: {clipe}')
    d = duracao(clipe)
    overlays = []  # (arquivo_webm, início, fim)

    if seg['tipo'] in ('apresentador', 'reporter'):
        cfg = {'mode': 'lower', 'nome': seg.get('nome', ''), 'funcao': seg.get('funcao', ''),
               'cidadeRotulo': seg.get('cidadeRotulo', '') if seg['tipo'] == 'apresentador' else info_cidade(seg)[2]}
        pasta = os.path.join(OBRA, f'legenda_{idx}_frames')
        quadros(cfg, DUR_LEGENDA, True, pasta)
        arq = os.path.join(OBRA, f'legenda_{idx}.webm')
        para_webm_alfa(pasta, arq)
        overlays.append((arq, 0.5, 0.5 + DUR_LEGENDA))

    for j, e in enumerate(seg.get('eventos', [])):
        ini = float(e['tempo'])
        dur_e = float(e.get('duracao', 4.0))
        if ini + dur_e > d:
            print(f'  aviso: evento {j + 1} do segmento {idx} ultrapassa o fim do clipe ({ini + dur_e:.1f} > {d:.1f} s)')
        cfg = dict(e, mode='event')
        pasta = os.path.join(OBRA, f'evento_{idx}_{j}_frames')
        quadros(cfg, dur_e, True, pasta)
        arq = os.path.join(OBRA, f'evento_{idx}_{j}.webm')
        para_webm_alfa(pasta, arq)
        overlays.append((arq, ini, ini + dur_e))

    # Enquadramento: vídeo centralizado sobre um fundo desfocado do próprio vídeo (sem barras pretas)
    partes = ['[0:v]split=2[fundo_src][frente_src];'
              '[fundo_src]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
              'boxblur=20:5,eq=brightness=-0.05[fundo];'
              '[frente_src]scale=1920:1080:force_original_aspect_ratio=decrease[frente];'
              '[fundo][frente]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v0]']
    cur = 'v0'
    for i, (_, ini, fim) in enumerate(overlays, start=1):
        partes.append(f'[{i}:v]format=yuva420p,setpts=PTS+{ini}/TB[o{i}]')
        partes.append(f"[{cur}][o{i}]overlay=0:0:eof_action=pass:format=auto:"
                      f"enable='between(t,{ini},{fim})'[v{i}]")
        cur = f'v{i}'
    # Tratamento de voz: passa-alta contra ruído grave, filtro de ruído, compressão e loudness -16 LUFS
    partes.append('[0:a]aresample=48000,highpass=f=90,lowpass=f=12000,afftdn=nf=-28,'
                  'acompressor=threshold=0.05:ratio=3:attack=15:release=250:makeup=2,'
                  'loudnorm=I=-16:TP=-1.5:LRA=9,aresample=48000,aformat=channel_layouts=stereo[a]')

    cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', clipe]
    for arq, _, _ in overlays:
        # libvpx-vp9 é obrigatório: o decodificador VP9 nativo ignora o canal alfa
        cmd += ['-c:v', 'libvpx-vp9', '-i', arq]
    cmd += ['-filter_complex', ';'.join(partes), '-map', f'[{cur}]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', saida_clipe]
    sh(cmd)
    return saida_clipe


def segmento_apresentador(seg, idx):
    clipe = os.path.join(OBRA, f'seg_{idx}_clipe.mp4')
    processa_clipe(seg, idx, clipe)
    saida = os.path.join(OBRA, f'seg_{idx}.mp4')
    finaliza(clipe, saida, entrada=True, saida_fade=True)
    return saida


def segmento_reporter(seg, idx):
    lon, lat, rotulo = info_cidade(seg)
    # 1) transição: mapa do Brasil com zoom até a cidade
    pasta = os.path.join(OBRA, f'mapa_{idx}_frames')
    quadros({'mode': 'map', 'lon': lon, 'lat': lat, 'cidadeRotulo': rotulo}, DUR_MAPA, False, pasta)
    mapa_v = os.path.join(OBRA, f'mapa_{idx}_v.mp4')
    para_mp4(pasta, mapa_v)
    whoosh = os.path.join(OBRA, f'whoosh_{idx}.wav')
    gera_whoosh(DUR_MAPA, 0.2, 1.4, whoosh)
    mapa = os.path.join(OBRA, f'mapa_{idx}.mp4')
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', mapa_v, '-i', whoosh,
        '-map', '0:v', '-map', '1:a', '-c:v', 'copy', '-c:a', 'aac', '-shortest', mapa])

    # 2) clipe do repórter com legenda, animações e áudio tratado
    clipe = os.path.join(OBRA, f'clipe_{idx}.mp4')
    processa_clipe(seg, idx, clipe)

    # 3) transição circular do mapa para o clipe
    junto = os.path.join(OBRA, f'seg_{idx}_bruto.mp4')
    off = DUR_MAPA - TRANSICAO_MAPA
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', mapa, '-i', clipe,
        '-filter_complex',
        f'[0:v][1:v]xfade=transition=circleopen:duration={TRANSICAO_MAPA}:offset={off}[v];'
        f'[0:a][1:a]acrossfade=d={TRANSICAO_MAPA}:c1=tri:c2=tri[a]',
        '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18',
        '-pix_fmt', 'yuv420p', '-r', '30', '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', junto])
    saida = os.path.join(OBRA, f'seg_{idx}.mp4')
    finaliza(junto, saida, entrada=True, saida_fade=True)
    return saida


def corta(src, ini, fim, saida):
    """Recorte preciso (re-codifica) de um trecho do clipe."""
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', src, '-ss', f'{ini}', '-to', f'{fim}',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', saida])


def segmento_dupla(seg, idx):
    """Um único arquivo com vários falantes: cada trecho recebe legenda e animações próprias,
    e a troca de falante acontece com uma transição (vídeo) e um sopro (áudio)."""
    src = seg['clipe']
    tr = seg.get('transicao', {})
    T = float(tr.get('duracao', 0.7))
    tipo_x = tr.get('tipo', 'slideleft')
    processados = []
    for k, p in enumerate(seg['partes']):
        bruto = os.path.join(OBRA, f'dupla_{idx}_{k}_bruto.mp4')
        corta(src, p['inicio'], p['fim'], bruto)
        sub = {'tipo': 'apresentador', 'clipe': bruto, 'nome': p.get('nome', ''),
               'funcao': p.get('funcao', ''), 'eventos': p.get('eventos', [])}
        out = os.path.join(OBRA, f'dupla_{idx}_{k}.mp4')
        processa_clipe(sub, idx * 10 + k, out)
        processados.append(out)

    atual = processados[0]
    for k in range(1, len(processados)):
        off = duracao(atual) - T
        ms = int(round(off * 1000))
        whoosh = os.path.join(OBRA, f'dupla_{idx}_sopro{k}.wav')
        gera_whoosh(T, 0.0, T, whoosh)
        novo = os.path.join(OBRA, f'dupla_{idx}_junta{k}.mp4')
        fc = (f'[0:v][1:v]xfade=transition={tipo_x}:duration={T}:offset={off:.3f}[v];'
              f'[0:a][1:a]acrossfade=d={T}:c1=tri:c2=tri[xa];'
              f'[2:a]adelay={ms}|{ms}[w];'
              f'[xa][w]amix=inputs=2:duration=first:normalize=0[a]')
        sh(['ffmpeg', '-y', '-loglevel', 'error', '-i', atual, '-i', processados[k], '-i', whoosh,
            '-filter_complex', fc, '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', '30',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', novo])
        atual = novo

    saida = os.path.join(OBRA, f'seg_{idx}.mp4')
    finaliza(atual, saida, entrada=True, saida_fade=True)
    return saida


def medir_loudness(caminho):
    p = subprocess.run(['ffmpeg', '-hide_banner', '-nostats', '-i', caminho,
                        '-af', 'ebur128=peak=true', '-f', 'null', '-'],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    m = re.findall(r'I:\s+(-?[\d.]+) LUFS', p.stderr)
    pk = re.findall(r'Peak:\s+(-?[\d.]+) dBFS', p.stderr)
    if m:
        print(f'Loudness integrado: {m[-1]} LUFS | pico: {pk[-1] if pk else "?"} dBFS')


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    with open(sys.argv[1], encoding='utf-8') as f:
        roteiro = json.load(f)
    os.makedirs(OBRA, exist_ok=True)
    saida = os.path.join(HERE, roteiro.get('saida', 'saida/Horizonte_Verde.mp4'))
    os.makedirs(os.path.dirname(saida), exist_ok=True)

    # caminhos de clipes são relativos à pasta do projeto, não ao diretório atual
    for s in roteiro['segmentos']:
        if 'clipe' in s:
            s['clipe'] = os.path.abspath(os.path.join(HERE, s['clipe']))
    faltando = [s['clipe'] for s in roteiro['segmentos'] if 'clipe' in s and not os.path.exists(s['clipe'])]
    if faltando:
        raise SystemExit('Clipes ausentes:\n  ' + '\n  '.join(faltando))

    partes = []
    for i, seg in enumerate(roteiro['segmentos']):
        tipo = seg['tipo']
        print(f'[{i + 1}/{len(roteiro["segmentos"])}] {tipo} {seg.get("nome", "")}')
        if tipo == 'abertura':
            partes.append(abertura(os.path.join(OBRA, f'seg_{i}.mp4')))
        elif tipo == 'apresentador':
            partes.append(segmento_apresentador(seg, i))
        elif tipo == 'reporter':
            partes.append(segmento_reporter(seg, i))
        elif tipo == 'dupla':
            partes.append(segmento_dupla(seg, i))
        else:
            raise SystemExit(f'Tipo de segmento desconhecido: {tipo}')

    lista = os.path.join(OBRA, 'lista.txt')
    with open(lista, 'w', encoding='utf-8') as f:
        for p in partes:
            f.write(f"file '{p}'\n")
    sh(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lista,
        '-c', 'copy', '-movflags', '+faststart', saida])
    print('Pronto:', saida)
    medir_loudness(saida)


if __name__ == '__main__':
    main()
