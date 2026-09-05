"""Lexical retriever + knowledge-point canonicalization.

Dev stage uses a lightweight BM25-style lexical scorer over RAGChunks /
Question text (works well for Chinese with character bigrams). The interface is
embedding-ready: when EMBEDDING_PROVIDER=bge, vectors replace the lexical score
and this module becomes the hybrid retrieval fusion point (see docs/ai/RAG.md).
"""
import math
import re
from collections import Counter

_word_re = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


def _char_bigrams(text: str) -> Counter:
    tokens = []
    for tok in _word_re.findall(text.lower()):
        if len(tok) <= 2:
            tokens.append(tok)
        else:
            # latin words keep whole form; CJK runs produce bigrams
            if re.fullmatch(r"[a-zA-Z0-9]+", tok):
                tokens.append(tok)
            else:
                tokens.extend(tok[i : i + 2] for i in range(len(tok) - 1))
    return Counter(tokens)


def lexical_score(query: str, doc: str) -> float:
    """Cosine similarity over character-bigram TF vectors. 0..1, cheap & robust."""
    q, d = _char_bigrams(query), _char_bigrams(doc)
    if not q or not d:
        return 0.0
    dot = sum(v * d.get(k, 0) for k, v in q.items())
    qn = math.sqrt(sum(v * v for v in q.values()))
    dn = math.sqrt(sum(v * v for v in d.values()))
    return dot / (qn * dn + 1e-9)


def normalize_kp_name(name: str) -> str:
    """Canonicalization step 1: surface-form normalization."""
    n = name.strip().lower()
    n = re.sub(r"[\s「」『』（）()\[\]、,，。.·:：'']+", " ", n)
    n = re.sub(r"\s+", "", n)
    return n
