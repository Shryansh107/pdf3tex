const $ = id => document.getElementById(id);
let selected = null, result = null, objectUrl = null, busy = false;
let compiling = false, compiledUrl = null, compiledPdf = null;
const actions = ['copy', 'download-tex', 'download-zip', 'compile'];

function clearCompiled() {
  if (compiledUrl) URL.revokeObjectURL(compiledUrl);
  compiledUrl = null; compiledPdf = null;
  $('compiled-preview').removeAttribute('src');
  $('compiled-preview').hidden = true;
  $('download-pdf').disabled = true;
  $('compile-results').hidden = true;
  $('compiler-log').textContent = '';
  $('compiler-details').hidden = true;
  $('compiler-details').open = false;
  $('comparison-result').hidden = true;
}

function clearOutput() {
  clearCompiled();
  result = null;
  $('source').value = '';
  $('source').hidden = true;
  $('empty-state').hidden = false;
  $('output-state').textContent = 'Waiting for PDF';
  $('output-state').classList.remove('ready');
  $('warnings').hidden = true;
  $('stats').textContent = $('conversion-mode').value === 'readable' ? 'Readable source · pdfLaTeX' : 'Layout: XeLaTeX + project ZIP';
  actions.forEach(id => $(id).disabled = true);
}
function error(message) { $('error').textContent = message; $('error').hidden = false; }
function choose(file) {
  if (busy || compiling || !file) return;
  $('error').hidden = true;
  if (!file.name.toLowerCase().endsWith('.pdf')) return error('Please choose a PDF file.');
  if (file.size > 20 * 1024 * 1024) return error('The PDF must be smaller than 20 MB.');
  selected = file;
  clearOutput();
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = URL.createObjectURL(file);
  $('file-title').textContent = file.name;
  $('file-detail').textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · Ready to convert`;
  $('pdf-preview').src = objectUrl;
  $('open-pdf').href = objectUrl;
  $('preview-wrap').hidden = false;
  $('reset').hidden = false;
  $('convert').disabled = false;
  $('status').textContent = 'Document ready. Let’s get the source.';
}
$('dropzone').addEventListener('click', () => $('file').click());
$('file').addEventListener('change', event => choose(event.target.files[0]));
['dragenter', 'dragover'].forEach(type => $('dropzone').addEventListener(type, event => {
  event.preventDefault(); if (!busy) $('dropzone').classList.add('dragging');
}));
['dragleave', 'drop'].forEach(type => $('dropzone').addEventListener(type, event => {
  event.preventDefault(); $('dropzone').classList.remove('dragging');
  if (type === 'drop') choose(event.dataTransfer.files[0]);
}));
$('reset').addEventListener('click', () => {
  if (busy || compiling) return;
  selected = null; clearOutput(); $('file').value = '';
  if (objectUrl) URL.revokeObjectURL(objectUrl);
  objectUrl = null;
  $('pdf-preview').removeAttribute('src');
  $('preview-wrap').hidden = true; $('reset').hidden = true;
  $('error').hidden = true; $('convert').disabled = true;
  $('file-title').textContent = 'Drop your PDF here';
  $('file-detail').textContent = 'or click to browse files';
  $('status').textContent = 'Choose a PDF to get started.';
});
$('convert').addEventListener('click', async () => {
  if (!selected || busy || compiling) return;
  busy = true; clearOutput(); $('error').hidden = true;
  $('conversion-mode').disabled = true;
  $('convert').disabled = true; $('dropzone').disabled = true; $('reset').disabled = true;
  $('convert').textContent = 'Converting…';
  $('output-state').textContent = 'Converting';
  const start = Date.now();
  const update = () => $('status').textContent = `Reconstructing LaTeX… ${Math.floor((Date.now() - start) / 1000)}s. Large documents can take longer.`;
  update(); const timer = setInterval(update, 1000);
  try {
    const form = new FormData(); form.append('file', selected); form.append('mode', $('conversion-mode').value);
    const response = await fetch('/api/convert', { method: 'POST', body: form });
    const payload = await response.json();
    if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Conversion failed. Please try again.');
    result = payload;
    $('source').value = result.tex;
    $('source').hidden = false; $('empty-state').hidden = true;
    $('output-state').textContent = 'Ready to edit'; $('output-state').classList.add('ready');
    $('stats').textContent = `${result.pages} page${result.pages === 1 ? '' : 's'} · ${result.images} illustrations · ${result.mode === 'readable' ? 'readable source · pdfLaTeX' : 'layout project ZIP'}`;
    $('status').textContent = 'Conversion complete. Review your source before compiling.';
    actions.forEach(id => $(id).disabled = false);
    if (result.warnings.length) { $('warnings').textContent = result.warnings.join(' '); $('warnings').hidden = false; }
  } catch (err) {
    error(err.message || 'Could not reach the server. Please try again.');
    $('status').textContent = 'Conversion could not be completed.';
    $('output-state').textContent = 'Try again';
  } finally {
    clearInterval(timer); busy = false;
    $('conversion-mode').disabled = false;
    $('convert').disabled = false; $('dropzone').disabled = false; $('reset').disabled = false;
    $('convert').innerHTML = 'Convert to LaTeX <span aria-hidden="true">↗</span>';
  }
});
$('copy').addEventListener('click', async () => {
  try { await navigator.clipboard.writeText($('source').value); $('copy').textContent = 'Copied!'; }
  catch { $('source').focus(); $('source').select(); $('copy').textContent = 'Press Ctrl/Cmd+C'; }
  setTimeout(() => $('copy').textContent = 'Copy code', 2500);
});
function download(blob, suffix) {
  const url = URL.createObjectURL(blob), a = document.createElement('a');
  a.href = url; a.download = selected.name.replace(/\.pdf$/i, '') + suffix;
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('download-tex').addEventListener('click', () => download(new Blob([$('source').value], {type:'application/x-tex;charset=utf-8'}), '.tex'));
$('download-zip').addEventListener('click', () => {
  const bytes = Uint8Array.from(atob(result.zip), char => char.charCodeAt(0));
  download(new Blob([bytes], {type:'application/zip'}), '-latex.zip');
});

function pdfBlob(encoded) {
  return new Blob([Uint8Array.from(atob(encoded), c => c.charCodeAt(0))], {type: 'application/pdf'});
}
function originalBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(',')[1]);
    reader.onerror = () => reject(new Error('Could not read the original PDF for comparison.'));
    reader.readAsDataURL(file);
  });
}
$('conversion-mode').addEventListener('change', () => {
  if (!selected || busy || compiling) return;
  clearOutput();
  $('status').textContent = 'Mode changed. Convert again to generate the new source.';
});
$('source').addEventListener('input', () => {
  if (!compiledPdf) return;
  clearCompiled();
  $('compile-results').hidden = false;
  $('compile-status').classList.remove('compile-failed');
  $('compile-status').textContent = 'Source changed. Compile again to preview and download the latest PDF.';
});
$('compile').addEventListener('click', async () => {
  if (!result || busy || compiling) return;
  compiling = true; clearCompiled();
  const tex = $('source').value;
  $('compile-results').hidden = false;
  $('compile-status').classList.remove('compile-failed');
  $('compile-status').textContent = `Compiling your current source with ${result.engine === 'pdflatex' ? 'pdfLaTeX (single .tex only)' : 'Tectonic'}…`;
  $('compile').textContent = 'Compiling…';
  ['compile', 'convert', 'dropzone', 'reset', 'conversion-mode'].forEach(id => $(id).disabled = true);
  $('source').readOnly = true;
  try {
    const response = await fetch('/api/compile', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tex, project_zip: result.mode === 'readable' ? '' : result.zip,
        engine: result.engine || 'tectonic', fidelity_target: result.fidelity_target || 95,
        original_pdf: await originalBase64(selected)})
    });
    const payload = await response.json();
    const detail = payload.detail;
    if (!response.ok) {
      const log = detail?.log || '';
      $('compiler-log').textContent = log;
      $('compiler-details').hidden = !log;
      $('compiler-details').open = !!log;
      throw new Error(typeof detail === 'string' ? detail : detail?.message || 'Compilation failed. Please check the source.');
    }
    compiledPdf = pdfBlob(payload.pdf);
    compiledUrl = URL.createObjectURL(compiledPdf);
    $('compiled-preview').src = compiledUrl;
    $('compiled-preview').hidden = false;
    $('download-pdf').disabled = false;
    $('compiler-log').textContent = payload.log;
    $('compiler-details').hidden = !payload.log;
    $('compile-status').textContent = `Compiled successfully with ${payload.engine}. Review the PDF and compiler log for layout or missing-character warnings.`;
    if (payload.comparison) {
      const comparison = payload.comparison;
      $('comparison-result').hidden = false;
      $('comparison-result').classList.toggle('match', result.mode !== 'readable' && comparison.matches);
      $('comparison-score').textContent = result.mode === 'readable' ? `${comparison.similarity.toFixed(2)}% visual match · readable source reflows` : `${comparison.similarity.toFixed(2)}% visual match · ${comparison.matches ? comparison.target + '% target met' : 'below ' + comparison.target + '% target'}`;
      $('comparison-metric').textContent = comparison.metric;
      $('comparison-pages').textContent = comparison.pages.map(page => `Page ${page.page}: ${page.similarity.toFixed(2)}%${page.reason ? ' — ' + page.reason : ''}`).join(' · ');
    }
  } catch (err) {
    $('compile-status').textContent = err.message || 'Could not reach the compiler.';
    $('compile-status').classList.add('compile-failed');
  } finally {
    compiling = false;
    ['compile', 'convert', 'dropzone', 'reset', 'conversion-mode'].forEach(id => $(id).disabled = false);
    $('source').readOnly = false;
    $('compile').textContent = 'Compile PDF';
  }
});
$('download-pdf').addEventListener('click', () => {
  if (compiledPdf) download(compiledPdf, '-compiled.pdf');
});
