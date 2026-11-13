"""Compare two complete evaluations of the same PDF corpus."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics


def compare(before, after):
    def inputs(report):
        return {r['input']: r['sha256'] for r in report['manifest']['inputs']}
    if inputs(before) != inputs(after):
        raise ValueError('Both evaluations must contain exactly the same input paths and hashes.')
    def records(report):
        result = {(r['input'], r['mode']): r for r in report['results']}
        if len(result) != len(report['results']):
            raise ValueError('Duplicate input/mode records in evaluation.')
        return result
    original, current = records(before), records(after)
    if original.keys() != current.keys() or len(current) != len(inputs(after)) * 2:
        raise ValueError('Each evaluation must contain both modes for every input.')
    changes, modes = [], {}
    for key, old in original.items():
        new = current[key]
        score_before = old.get('metrics', {}).get('similarity', 0) if old['status'] == 'success' else 0
        score_after = new.get('metrics', {}).get('similarity', 0) if new['status'] == 'success' else 0
        changes.append({'input': key[0], 'mode': key[1], 'before_status': old['status'], 'after_status': new['status'],
                        'before_score': score_before, 'after_score': score_after, 'delta': round(score_after-score_before, 3),
                        'before_pass': old['status'] == 'success' and old.get('metrics', {}).get('matches', False),
                        'after_pass': new['status'] == 'success' and new.get('metrics', {}).get('matches', False)})
    for mode in ('layout', 'portable'):
        rows = [c for c in changes if c['mode'] == mode]
        paired = [c for c in rows if c['before_status'] == c['after_status'] == 'success']
        transitions = Counter(c['before_status'] + ' -> ' + c['after_status'] for c in rows)
        modes[mode] = {
            'before': before['summary'][mode], 'after': after['summary'][mode],
            'new_compiles': sum(c['before_status'] != 'success' and c['after_status'] == 'success' for c in rows),
            'lost_compiles': sum(c['before_status'] == 'success' and c['after_status'] != 'success' for c in rows),
            'new_passes': sum(not c['before_pass'] and c['after_pass'] for c in rows),
            'lost_passes': sum(c['before_pass'] and not c['after_pass'] for c in rows),
            'paired_successes': len(paired),
            'paired_mean_score_before': round(statistics.mean(c['before_score'] for c in paired), 3) if paired else None,
            'paired_mean_score_after': round(statistics.mean(c['after_score'] for c in paired), 3) if paired else None,
            'paired_improved_over_1pp': sum(c['delta'] > 1 for c in paired),
            'paired_regressed_over_1pp': sum(c['delta'] < -1 for c in paired),
            'status_transitions': dict(sorted(transitions.items())),
        }
    return {'documents': len(inputs(after)), 'before_pipeline': before['manifest']['pipeline_sha256'],
            'after_pipeline': after['manifest']['pipeline_sha256'], 'modes': modes, 'changes': changes}


TEMPLATE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PDF3TeX improvement comparison</title><style>
body{margin:0;font-family:var(--font-sans,system-ui);color:var(--foreground)}*{box-sizing:border-box}
p{line-height:1.5;margin:0 0 16px}.muted,.note{color:var(--muted-foreground)}
.controls{display:flex;gap:12px;align-items:center;flex-wrap:wrap}select{color:var(--foreground);background:var(--secondary);font:inherit;border:1px solid var(--border);border-radius:var(--radius,8px);padding:8px}
.chart{height:260px;display:flex;flex-direction:column;justify-content:center;gap:18px}.row{display:grid;grid-template-columns:112px 1fr 70px;gap:10px;align-items:center;font-size:13px}
.track{height:26px;border-radius:4px;background:var(--secondary);overflow:hidden}.bar{height:100%;background:var(--chart-1);transition:width .2s}.before{background:var(--chart-2)}
.value{text-align:right;font-variant-numeric:tabular-nums}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:right;border-bottom:1px solid var(--border);padding:10px 5px}th:first-child,td:first-child{text-align:left}th{color:var(--muted-foreground);font-weight:500}.note{font-size:12px;margin-top:16px}
.details{margin-top:20px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius,8px);padding:16px}.details p{margin-bottom:8px}button{font:inherit;border:1px solid var(--border);background:var(--secondary);color:var(--foreground);border-radius:var(--radius,8px);padding:6px 10px;cursor:pointer}
@media(max-width:480px){.row{grid-template-columns:90px 1fr 58px;gap:6px}table{font-size:11px}th,td{padding:9px 3px}}
</style></head><body><p><strong>__COUNT__ PDFs: baseline and milestone 1</strong><br><span class="muted">Identical inputs, compiler images, similarity metric, and pass thresholds.</span></p>
<div class="controls"><label for="metric">Measure</label><select id="metric"><option value="dataset_score">Overall visual score</option><option value="compiled_percent">Compilation success rate</option><option value="pass_percent">Documents meeting target</option><option value="successful_mean_lowest_page_ssim">Visual score among compiled PDFs</option></select></div>
<div class="chart" id="chart"></div><table><thead><tr><th>Mode</th><th>Compiled</th><th>Meets target</th><th>Score</th><th>Grade</th></tr></thead><tbody id="table"></tbody></table>
<div class="details"><div class="controls"><strong>Paired outcomes</strong><button id="toggle">Show portable</button></div><p id="paired"></p><p class="note" id="regressions"></p></div>
<p class="note">Overall score averages each input's lowest page foreground SSIM; failed or rejected inputs count as zero. Portable passes at 90%, layout at 95%. A ≥90, B ≥80, C ≥70, D ≥60, F &lt;60. Visual fidelity does not establish editable text or semantic LaTeX recovery. Compiled-only groups can change between runs.</p>
<script>const data=__DATA__;const modes=data.modes;let detail='layout';const byId=id=>document.getElementById(id);
function render(){let key=byId('metric').value;byId('chart').innerHTML=Object.entries(modes).flatMap(([name,m])=>['before','after'].map(phase=>{let value=m[phase][key];return `<div class="row"><span>${name} · ${phase==='before'?'baseline':'improved'}</span><div class="track"><div class="bar ${phase}" style="width:${value}%"></div></div><span class="value">${value.toFixed(2)}%</span></div>`})).join('');}
byId('table').innerHTML=Object.entries(modes).flatMap(([name,m])=>['before','after'].map(phase=>{let s=m[phase];return `<tr><td>${name} · ${phase==='before'?'baseline':'improved'}</td><td>${s.compiled}/${s.documents}</td><td>${s.passed}/${s.documents}</td><td>${s.dataset_score.toFixed(2)}%</td><td>${s.grade}</td></tr>`})).join('');
function details(){let m=modes[detail];byId('paired').textContent=`${detail}: ${m.new_compiles} newly compiled, ${m.lost_compiles} lost compiles; ${m.new_passes} new visual passes, ${m.lost_passes} lost passes.`;byId('regressions').textContent=`Among ${m.paired_successes} PDFs that compiled in both runs, mean score changed from ${m.paired_mean_score_before?.toFixed(2)}% to ${m.paired_mean_score_after?.toFixed(2)}%. ${m.paired_improved_over_1pp} improved by more than 1 point; ${m.paired_regressed_over_1pp} regressed by more than 1 point.`;byId('toggle').textContent='Show '+(detail==='layout'?'portable':'layout');}
byId('metric').onchange=render;byId('toggle').onclick=()=>{detail=detail==='layout'?'portable':'layout';details()};render();details();</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    before, after = [json.loads(p.read_text(encoding='utf-8')) for p in (args.before, args.after)]
    result = compare(before, after)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    compact = {k:v for k,v in result.items() if k != 'changes'}
    page = TEMPLATE.replace('__COUNT__', f'{result["documents"]:,}').replace('__DATA__', json.dumps(compact).replace('<', '\\u003c'))
    (args.output / 'comparison.html').write_text(page, encoding='utf-8')
    lines = ['# Milestone 1 comparison', '', f'All {result["documents"]:,} input paths and SHA-256 hashes match the baseline.', '',
             '| Mode | Run | Compiled | Meets target | Overall score | Grade |', '| --- | --- | ---: | ---: | ---: | :---: |']
    for mode, values in result['modes'].items():
        for phase in ('before', 'after'):
            s = values[phase]
            lines.append(f'| {mode} | {phase} | {s["compiled"]} | {s["passed"]} | {s["dataset_score"]:.3f}% | {s["grade"]} |')
    lines += ['', 'Overall score averages the minimum page foreground SSIM for every PDF; failures and rejections count as zero. Portable passes at 90%; layout at 95%. Metrics and input limits are unchanged.', '', '## Gains and regressions', '']
    for mode, m in result['modes'].items():
        lines += [f'- **{mode}:** {m["new_compiles"]} new compiles, {m["lost_compiles"]} lost compiles; {m["new_passes"]} new visual passes, {m["lost_passes"]} visual passes lost.',
                  f'  Among {m["paired_successes"]} inputs compiled in both runs, {m["paired_improved_over_1pp"]} improved and {m["paired_regressed_over_1pp"]} regressed by more than 1 percentage point. Mean minimum-page SSIM: {m["paired_mean_score_before"]}% → {m["paired_mean_score_after"]}%.']
    lines += ['', 'Full per-input changes and status transitions are in [comparison.json](comparison.json). Open [comparison.html](comparison.html) for the interactive chart. See [results.json](results.json) for all current scores and [the baseline](../kaggle/FINDINGS.md) for the original findings.', '',
              '## Largest coverage-adjusted regressions', '', '| Mode | PDF | Before | After | Current outcome |', '| --- | --- | ---: | ---: | --- |']
    for mode in ('layout', 'portable'):
        for row in sorted((c for c in result['changes'] if c['mode'] == mode and c['delta'] < 0), key=lambda c:c['delta'])[:5]:
            lines.append(f'| {mode} | `{row["input"]}` | {row["before_score"]}% | {row["after_score"]}% | {row["after_status"]} |')
    (args.output / 'COMPARISON.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(compact, indent=2))


if __name__ == '__main__':
    main()
