"""Divide textos em trechos: um por paragrafo; paragrafos longos sao quebrados
em sentencas ate ~TAMANHO caracteres."""
import glob
import os
import re

TAMANHO = 500


def dividir(texto, tamanho=TAMANHO):
    trechos = []
    for par in re.split(r"\n\s*\n", texto):
        par = " ".join(par.split())
        if not par:
            continue
        if len(par) <= tamanho:
            trechos.append(par)
            continue
        atual = ""
        for sent in re.split(r"(?<=[.!?])\s+", par):
            if atual and len(atual) + len(sent) + 1 > tamanho:
                trechos.append(atual)
                atual = sent
            else:
                atual = f"{atual} {sent}".strip()
        if atual:
            trechos.append(atual)
    return trechos


def carregar_diretorio(diretorio):
    """Le diretorio/*.txt e devolve [{"texto","origem"}] com origem = nome do arquivo."""
    docs = []
    for caminho in sorted(glob.glob(os.path.join(diretorio, "*.txt"))):
        with open(caminho, encoding="utf-8") as f:
            for trecho in dividir(f.read()):
                docs.append({"texto": trecho, "origem": os.path.basename(caminho)})
    return docs
