from pathlib import Path

import numpy as np
import sklearn

ROOT = Path(__file__).resolve().parents[1]


def test_installed_sklearn_matches_pickle_pin():
    recorded = (
        (ROOT / "models" / "sklearn_version.txt")
        .read_text(encoding="utf-8")
        .splitlines()[0]
        .strip()
    )
    assert sklearn.__version__ == recorded, (
        f"sklearn instalado={sklearn.__version__}; pickle treinado em {recorded}. "
        "Ajuste requirements-test.txt (scikit-learn==…) ou retreine o notebook 03."
    )


def test_numpy_is_1x_for_pickle():
    major = int(np.__version__.split(".")[0])
    assert major < 2, (
        f"numpy instalado={np.__version__}; o pickle usa numpy.core.multiarray (NumPy 1.x). "
        "Ajuste requirements-test.txt (numpy>=1.24,<2) ou retreine o notebook 03."
    )
