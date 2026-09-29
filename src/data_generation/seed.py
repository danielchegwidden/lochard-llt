"""Load docs/Sample Data.xlsx – the 400 rows Lochard supplied – as golden seed rows and vocabularies."""
from __future__ import annotations

import os

import pandas as pd

import config as C

def load() -> dict[str, pd.DataFrame]:
    for p in [os.environ.get("LOCHARD_SAMPLE_XLSX", ""), "docs/Sample Data.xlsx"]:
        if p and os.path.exists(p):
            # keep literal 'null' strings exactly as the source system emits them
            return pd.read_excel(p, sheet_name=None, keep_default_na=False)
    raise FileNotFoundError("Sample Data.xlsx not found (set LOCHARD_SAMPLE_XLSX)")


def pseudonymise_actionees(obs: pd.DataFrame, people: pd.DataFrame) -> pd.DataFrame:
    """Sample actionees may be real staff – map each to a consistent fictitious username."""
    names = sorted(obs["actionee"].unique())
    pool = people["username"].tolist()
    mapping = {n: pool[i % len(pool)] for i, n in enumerate(names)}
    out = obs.copy()
    out["actionee"] = out["actionee"].map(mapping)
    return out


def description_vocab(actuals: pd.DataFrame) -> dict[int, list[str]]:
    vocab: dict[int, list[str]] = {}
    for acc, grp in actuals.groupby("account_key"):
        vocab[int(acc)] = sorted(set(grp["description"].astype(str)))
    return vocab
