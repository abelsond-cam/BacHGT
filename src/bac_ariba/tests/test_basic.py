"""Smoke tests: package imports and exposes expected submodules."""

import bac_ariba


def test_version():
    assert isinstance(bac_ariba.__version__, str)
    assert bac_ariba.__version__


def test_submodules():
    assert hasattr(bac_ariba, "pp")
    assert hasattr(bac_ariba, "tl")
    assert hasattr(bac_ariba, "pl")
