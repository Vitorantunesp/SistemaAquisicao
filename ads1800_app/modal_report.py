"""Self-contained, printable modal report; figures use saved identification data."""
from datetime import datetime
from html import escape
from io import StringIO
from pathlib import Path
import os
import tempfile

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_svg import FigureCanvasSVG


def number(value, digits=5):
    return f'{value:.{digits}g}' if value is not None and np.isfinite(value) else 'Não disponível'


def table(headers, rows):
    def cells(values, tag):
        return ''.join(f'<{tag}>{escape(str(v))}</{tag}>' for v in values)
    return '<table><thead><tr>'+cells(headers, 'th')+'</tr></thead><tbody>'+''.join(
        '<tr>'+cells(row, 'td')+'</tr>' for row in rows)+'</tbody></table>'


def svg(figure):
    stream = StringIO()
    FigureCanvasSVG(figure).print_svg(stream)
    content = stream.getvalue()
    return content[content.index('<svg'):]


def date_label(value):
    if not value:
        return 'Não informado'
    try:
        return datetime.fromisoformat(value).strftime('%d/%m/%Y %H:%M:%S %z')
    except (ValueError, TypeError):
        return str(value)


def generate_report(session, result, path, identification='MISO', reference=0):
    if not result or not result['modes']:
        raise ValueError('Calcule e selecione pelo menos um modo antes de gerar o relatório.')
    c = session.config
    now = datetime.now().astimezone()
    sensor_names = [s['name'] for s in c.sensors]
    used_sources = {s['file'] for s in result.get('source_records', [])}
    used_points = set(result.get('shape_point_ids', result['point_ids']))
    reference_label = 'Todos os acelerômetros' if identification == 'MIMO' else sensor_names[reference]
    sections = ['<h1>Relatório de análise modal por impacto</h1>',
        '<p>Roving hammer · estrutura plana · força e acelerações normais ao plano XY.</p>',
        '<h2>1. Dados do ensaio</h2>', table(['Campo', 'Valor'], [
            ['Ensaio', session.directory.name], ['Pasta de origem', str(session.directory)],
            ['Execução — início (fuso registrado)', date_label(session.metadata.get('acquisition_started_at'))],
            ['Criação/importação da sessão', date_label(session.metadata.get('session_created_at'))],
            ['Relatório gerado em', date_label(now.isoformat())],
            ['Temperatura ambiente no início [°C]', 'Não informado' if c.ambient_temperature_c is None else number(c.ambient_temperature_c)],
            ['Equipamento/origem', session.metadata.get('mode', 'Não informado')],
            ['Arquivo importado', session.metadata.get('source', 'Não se aplica')],
            ['Identificação', identification], ['Referência', reference_label],
            ['Método', result['method']], ['Biblioteca', str(result.get('library', 'Método interno'))],
            ['Batidas utilizadas no ajuste', len(used_sources)],
            ['Amostragem [Hz]', number(c.sample_rate)], ['Duração por captura [s]', number(c.duration)],
            ['Pré-trigger [s]', number(c.pretrigger)], ['Trigger atual [N]', number(c.threshold)],
            ['Polaridade', c.polarity], ['Janela de força / resposta', f'{c.force_window} / {c.response_window}'],
            ['Passa-banda', f'{c.low_cut:g}–{c.high_cut:g} Hz' if c.bandpass_enabled else 'Desativado'],
            ['Faixa do ajuste [Hz]', f"{result['settings']['fmin']:g}–{result['settings']['fmax']:g}"],
            ['Resolução espectral [Hz]', number(result['frequency_resolution_hz'])],
            ['Exponencial comum — resíduo final', number(result['settings']['exponential_end'])],
            ['Coerência mínima configurada', number(result['settings']['min_coherence'])],
            ['Mínimo de batidas por ponto', result['settings']['min_hits']],
        ]), '<h2>2. Geometria e pontos</h2>',
        '<p>Coordenadas XY em metros. Os graus de liberdade medidos são em Z. Posições dos sensores não representam apoios.</p>',
        table(['Ponto de impacto', 'X [m]', 'Y [m]', 'Usado no ajuste', 'Aceitas / rejeitadas / pendentes'],
              [[name, number(x), number(y), 'Sim' if name in used_points else 'Não',
                ' / '.join(str(sum(r['point'] == name and r['status'] == state for r in session.records))
                           for state in ['aceita', 'rejeitada', 'pendente'])] for name, x, y in c.points]),
        table(['Acelerômetro', 'Canal', 'X [m]', 'Y [m]', 'Fator SI', 'Usado no ajuste'],
              [[s['name'], s['channel']+1, *map(number, s['position']), number(s['factor']),
                'Sim' if identification == 'MIMO' or i == reference else 'Não'] for i, s in enumerate(c.sensors)]),
        table(['Vértice do contorno', 'X [m]', 'Y [m]'], [[i, number(x), number(y)] for i, (x, y) in enumerate(c.outline, 1)])]
    fig = Figure(figsize=(8, 4), layout='constrained')
    ax = fig.subplots()
    outline = np.asarray([*c.outline, c.outline[0]])
    ax.plot(outline[:, 0], outline[:, 1], color='gray')
    for name, x, y in c.points:
        ax.plot(x, y, 'o', color='#2563eb')
        ax.annotate(name, (x, y), xytext=(5, 6), textcoords='offset points')
    for s in c.sensors:
        x, y = s['position']
        ax.plot(x, y, 'x', color='#16a34a', markersize=10)
        ax.annotate(s['name'], (x, y), xytext=(5, -12), textcoords='offset points')
    ax.set(xlabel='X [m]', ylabel='Y [m]', title='Pontos de impacto (azul) e acelerômetros (verde)')
    ax.set_aspect('equal', adjustable='datalim')
    ax.grid(alpha=.2)
    sections += [svg(fig), '<h2>3. Frequências naturais e amortecimentos</h2>',
        table(['Modo', 'Natural [Hz]', 'Amortecida [Hz]', 'Amortecimento ζ [%]', 'Alertas'],
              [[i, number(m['frequency_hz']), number(m['damped_frequency_hz']), number(100*m['damping_ratio']),
                '; '.join(m['warnings']) or 'Sem alertas específicos'] for i, m in enumerate(result['modes'], 1)]),
        '<h2>4. Coerência e qualidade do ajuste</h2>',
        '<p>Estatísticas sobre bins finitos na faixa analisada, sem esconder os valores abaixo do limite de coerência. '
        'Nos modos, usa-se o bin mais próximo da frequência natural. Com uma só batida, a coerência não está disponível.</p>']
    f = np.asarray(result['frequency'])
    band = (f >= result['settings']['fmin']) & (f <= result['settings']['fmax'])
    rows, modal_coherences = [], []
    for label, coherence in zip(result['point_ids'], result['coherence']):
        valid = coherence[band & np.isfinite(coherence)]
        rows.append([label, number(valid.min() if len(valid) else None), number(valid.mean() if len(valid) else None),
                     number(100*result['relative_fit_error'][label] if result['relative_fit_error'][label] is not None else None)])
        for i, mode in enumerate(result['modes'], 1):
            nearest = np.argmin(abs(f-mode['frequency_hz']))
            modal_coherences.append([label, i, number(mode['frequency_hz']), number(f[nearest]), number(coherence[nearest])])
    sections.append(table(['FRF', 'Coerência mínima', 'Coerência média', 'Erro FRF [%]'], rows))
    sections.append(table(['FRF', 'Modo', 'Natural [Hz]', 'Bin avaliado [Hz]', 'Coerência'], modal_coherences))
    for start in range(0, len(result['point_ids']), 6):
        fig = Figure(figsize=(9, 3.5), layout='constrained')
        ax = fig.subplots()
        for i in range(start, min(start+6, len(result['point_ids']))):
            ax.plot(f[band], result['coherence'][i, band], label=result['point_ids'][i])
        for m in result['modes']:
            ax.axvline(m['frequency_hz'], color='#9333ea', linestyle='--', alpha=.5)
        ax.set(xlabel='Frequência [Hz]', ylabel='Coerência γ²', ylim=(0, 1.05),
               xlim=(result['settings']['fmin'], result['settings']['fmax']))
        ax.legend(fontsize=8)
        ax.grid(alpha=.2)
        sections.append(svg(fig))
    sections += ['<h2>5. Formas modais e coordenadas</h2>',
                 '<p>Formas relativas, sem normalização por massa. Z modal é adimensional, não deslocamento em metros. '
                 'As figuras mostram a parte real (fase 0°); as tabelas preservam a forma complexa. '
                 'Pontos sem estimativa não são tratados como deslocamento zero. No MIMO, entradas e saídas têm escalas próprias.</p>']
    for i, mode in enumerate(result['modes'], 1):
        sections.append(f'<section class="mode"><h3>Modo {i} — {mode["frequency_hz"]:.5g} Hz · ζ = {100*mode["damping_ratio"]:.5g}%</h3>')
        fig = Figure(figsize=(8, 4.5), layout='constrained')
        ax = fig.add_subplot(projection='3d')
        ax.plot(outline[:, 0], outline[:, 1], np.zeros(len(outline)), color='gray', alpha=.5)
        mode_rows = []
        for name, x, y in c.points:
            real = mode['shape'].get(name)
            imag = mode.get('shape_imag', {}).get(name, 0) if real is not None else None
            mode_rows.append([name, number(x), number(y), number(real), number(imag),
                              number(abs(complex(real, imag)) if real is not None else None)])
            if real is not None:
                ax.plot([x, x], [y, y], [0, real], color='#2563eb')
                ax.scatter([x], [y], [real], color='#2563eb')
                ax.text(x, y, real, name)
        ax.set(xlabel='X [m]', ylabel='Y [m]', zlabel='Z modal relativo (real)', zlim=(-1.1, 1.1))
        sections += [svg(fig), table(['Impacto', 'X [m]', 'Y [m]', 'Z real', 'Z imaginário', '|Z|'], mode_rows)]
        if mode.get('output_shape'):
            sections.append(table(['Acelerômetro', 'X [m]', 'Y [m]', 'Z real (saída)', 'Z imaginário (saída)'],
                [[s['name'], *map(number, s['position']), number(mode['output_shape'].get(s['name'])),
                  number(mode['output_shape_imag'].get(s['name']))] for s in c.sensors]))
            sections.append(f'<p>Erro da aproximação de posto 1 dos resíduos: {100*mode["residue_rank_one_error"]:.3g}%.</p>')
        sections.append('</section>')
    sections += ['<h2>6. Rastreabilidade e observações</h2>',
        table(['Ponto', 'Arquivo de captura usado', 'Estado', 'Trigger [N]', 'Alertas'],
            [[r['point'], r['file'], r['status'], number(r.get('trigger', {}).get('threshold_N')),
              '; '.join(r.get('issues', [])) or 'Sem alertas'] for r in session.records if r['file'] in used_sources]),
        '<ul>'+''.join('<li>'+escape(str(w))+'</li>' for w in result['warnings'])+'</ul>',
        '<p>Relatório do resultado selecionado no momento da exportação. Alterações posteriores nas batidas ou no ajuste não atualizam este arquivo. '
        'Estabilidade numérica e coerência alta não certificam isoladamente um modo físico.</p>']
    html = '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>Relatório modal</title>
<style>body{font:14px Arial,sans-serif;color:#172033;max-width:1100px;margin:36px auto;padding:0 24px;line-height:1.5}
h1,h2,h3{color:#173e69}h2{margin-top:32px;border-bottom:2px solid #d9e2ec}table{border-collapse:collapse;width:100%;margin:14px 0;font-size:12px}
th,td{border:1px solid #cbd5e1;padding:7px;text-align:left;overflow-wrap:anywhere}th{background:#edf2f7}svg{max-width:100%;height:auto}
thead{display:table-header-group}tr{break-inside:avoid}h2,h3{break-after:avoid}@media print{body{margin:0;font-size:11px}svg{max-height:130mm}table{font-size:9px}.mode{break-before:page}@page{size:A4;margin:15mm}}
</style></head><body>'''+''.join(sections)+'</body></html>'
    path = Path(path)
    # Replace only a fully written report; preserve any previous file on failure.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.relatorio_', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return path
