from pathlib import Path

import SI_AI_smc as engine


def test_active_engine_is_futures_only_and_uses_usdm_exchange():
    assert engine.MARKETS == ["FUTURES"]
    assert set(engine.EXCHANGES) == {"FUTURES"}
    assert engine.EXCHANGES["FUTURES"].id == "binanceusdm"


def test_obsolete_spot_smc_engine_is_not_shipped():
    project_dir = Path(__file__).resolve().parent
    assert not (project_dir / "smc.py").exists()
