from types import SimpleNamespace
from pathlib import Path

import pymupdf
import pytest

import compiler
from scripts.evaluate_dataset import aggregate, text_metrics


@pytest.mark.parametrize('system, expected', [('nt', []), ('posix', ['--user', '1000:1001'])])
def test_compiler_uses_host_user_only_on_posix(monkeypatch, system, expected):
    commands = []
    monkeypatch.setattr(compiler, 'os', SimpleNamespace(name=system, getuid=lambda: 1000, getgid=lambda: 1001))
    monkeypatch.setattr(compiler.shutil, 'which', lambda _: 'docker')
    def run(command, **kwargs):
        commands.append(command)
        if 'run' in command:
            mount = command[command.index('--mount') + 1]
            directory = Path(mount.removeprefix('type=bind,src=').removesuffix(',dst=/work'))
            with pymupdf.open() as document:
                document.new_page()
                document.save(directory / 'main.pdf')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(compiler.subprocess, 'run', run)
    compiler.compile_latex('source', engine='pdflatex')
    assert len(commands) == 3  # Two compilation passes and guaranteed cleanup.
    if expected:
        index = commands[0].index('--user')
        assert commands[0][index:index + 2] == expected
    else:
        assert '--user' not in commands[0]
    assert commands[-1][:3] == ['docker', 'rm', '-f']


def test_dataset_grade_counts_failures_and_reports_eligible_subset():
    inventory = [{'input': 'good.pdf', 'text_tokens': 10}, {'input': 'bad.pdf'},
                 {'input': 'long.pdf', 'limit_error': 'Too many pages'}]
    records = [
        {'input': 'good.pdf', 'mode': 'portable', 'status': 'success',
         'metrics': {'similarity': 96, 'mean_page_similarity': 98, 'matches': True, 'text_token_f1': 100}},
        {'input': 'bad.pdf', 'mode': 'portable', 'status': 'conversion_failed'},
        {'input': 'long.pdf', 'mode': 'portable', 'status': 'input_rejected'},
    ]
    summary = aggregate(records, inventory)['portable']
    assert summary['dataset_score'] == 32
    assert summary['eligible_dataset_score'] == 48
    assert summary['successful_mean_lowest_page_ssim'] == 96
    assert summary['passed'] == 1
    assert summary['grade'] == 'F'


def test_text_metric_has_no_ground_truth_for_image_only_pdf():
    with pymupdf.open() as document:
        document.new_page()
        data = document.tobytes()
    result = text_metrics(data, data)
    assert result['reference_tokens'] == 0
    assert result['text_token_f1'] is None
    assert result['text_token_recall'] is None
