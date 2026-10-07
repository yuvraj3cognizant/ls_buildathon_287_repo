import pytest

from src.utils.exceptions import SQLValidationError
from src.utils.validators import validate_readonly_sql


def test_valid_select_passes():
    sql = "SELECT trial_id, trial_name FROM clinical_trials WHERE status = 'ACTIVE'"
    assert validate_readonly_sql(sql).lower().startswith("select")


def test_valid_cte_passes():
    sql = "WITH x AS (SELECT trial_id FROM clinical_trials) SELECT * FROM x"
    assert validate_readonly_sql(sql)


def test_rejects_insert():
    with pytest.raises(SQLValidationError):
        validate_readonly_sql("INSERT INTO clinical_trials VALUES (1)")


def test_rejects_drop():
    with pytest.raises(SQLValidationError):
        validate_readonly_sql("DROP TABLE clinical_trials")


def test_rejects_unknown_table():
    with pytest.raises(SQLValidationError):
        validate_readonly_sql("SELECT * FROM some_other_table")


def test_rejects_empty():
    with pytest.raises(SQLValidationError):
        validate_readonly_sql("   ")
