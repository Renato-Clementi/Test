"""Sopralluogo, modulo MOSAIKA.

Checklist di cantiere come dati (non come codice): un modello si importa
da YAML o JSON, un rilievo è un'istanza per un sito. I file stanno su un
backend sostituibile, i metadati su PostgreSQL. Nessuna chiamata a Odoo:
l'id opportunità, se c'è, è solo un numero memorizzato.
"""
