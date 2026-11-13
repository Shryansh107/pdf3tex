"""Page-aligned visual comparison; blank margins do not inflate the score."""
import numpy as np
import pymupdf
from scipy.ndimage import binary_dilation
from skimage.metrics import structural_similarity


def compare_pdfs(original, compiled):
    pages = []
    with pymupdf.open(stream=original, filetype='pdf') as reference, pymupdf.open(stream=compiled, filetype='pdf') as candidate:
        for index in range(max(len(reference), len(candidate))):
            if index >= len(reference) or index >= len(candidate):
                pages.append({'page': index+1, 'similarity': 0.0, 'reason': 'Page missing in one PDF.'})
                continue
            images = []
            scale = min(2, 2200 / max(max(doc[index].rect.width,doc[index].rect.height) for doc in [reference,candidate]))
            for doc in [reference, candidate]:
                pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(scale,scale), colorspace=pymupdf.csGRAY, alpha=False)
                images.append(np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width))
            height = max(im.shape[0] for im in images)
            width = max(im.shape[1] for im in images)
            padded = []
            for im in images:
                canvas = np.full((height,width),255,dtype=np.uint8)
                canvas[:im.shape[0],:im.shape[1]] = im
                padded.append(canvas)
            mask = binary_dilation((padded[0] < 245) | (padded[1] < 245), iterations=2)
            _, ssim_map = structural_similarity(*padded, data_range=255, full=True)
            score = float(ssim_map[mask].mean()) if mask.any() else 1.0
            if images[0].shape != images[1].shape:
                score *= min(im.size for im in images) / max(im.size for im in images)
            pages.append({'page':index+1,'similarity':round(max(0,score)*100,3)})
        score = min(p['similarity'] for p in pages)
        return {'similarity':score,'target':95,'matches':score>=95,
                'metric':'Foreground SSIM at up to 144 dpi (2200px cap); lowest page score. Blank margins excluded.', 'pages':pages}
