import danalyze


def test_import_succeeds():
    assert danalyze is not None


def test_version():
    assert danalyze.__version__ == "0.1.0"
