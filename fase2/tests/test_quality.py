import pandas as pd

from quality.validations import (
    VALID_STATES,
    check_not_null,
    check_referential_integrity,
    check_unique_key,
    check_valid_categories,
    check_value_range,
    run_quality_checks,
)


def _ok_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "municipality_id": ["1100015", "1100023"],
            "year": [2023, 2024],
            "literacy_rate": [60.0, 61.0],
            "state_code": ["RO", "RO"],
        }
    )


def test_quality_gate_passes_on_clean_table():
    df = _ok_frame()
    report = run_quality_checks(df, {"1100015", "1100023"}, VALID_STATES)
    assert report.passed


def test_quality_gate_fails_out_of_range():
    df = _ok_frame()
    df.loc[0, "literacy_rate"] = 140
    result = check_value_range(df, "literacy_rate", 0, 100)
    assert not result.passed


def test_quality_gate_fails_duplicate_key():
    df = pd.concat([_ok_frame(), _ok_frame().iloc[[0]]], ignore_index=True)
    result = check_unique_key(df, ("municipality_id", "year"))
    assert not result.passed


def test_quality_gate_fails_null_and_bad_state():
    df = _ok_frame()
    df.loc[0, "literacy_rate"] = None
    assert not check_not_null(df, ("municipality_id", "year", "literacy_rate")).passed
    df2 = _ok_frame()
    df2.loc[0, "state_code"] = "XX"
    assert not check_valid_categories(df2, "state_code", VALID_STATES).passed


def test_referential_integrity():
    df = _ok_frame()
    ok = check_referential_integrity(df, "municipality_id", {"1100015", "1100023"}, "municipalities")
    bad = check_referential_integrity(df, "municipality_id", {"1100015"}, "municipalities")
    assert ok.passed
    assert not bad.passed
