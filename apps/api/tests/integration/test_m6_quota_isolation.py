"""FR-MDL-020 AC3 evidence (M6): MDL writes only MDL, audit and session rows.

QTA/CRT do not exist yet, so "the tester's allowance is unchanged" cannot be shown end to
end. This test gives the strongest evidence available now: a statement-level trigger on
**every** table in the schema records each table an operation writes. Because triggers
are attached to whatever tables exist when the test runs, any quota or credit table that
a later phase adds is covered automatically: the test then fails if MDL ever writes it.
"""

from psycopg import sql

from .test_m3_mdl_api import mdl as mdl
from .test_m4_connection_tests import add_model, local_provider, run_test
from .test_m4_connection_tests import m4 as m4
from .test_m5_routing import put
from .test_wp2_database import connect
from .test_wp5_directory import auth_db as auth_db
from .test_wp5_directory import bootstrapped as bootstrapped
from .test_wp5_directory import directory as directory
from .test_wp5_directory import pytestmark

pytestmark = pytestmark


def install_write_log(db):
    with connect(db.owner) as connection:
        connection.execute("CREATE TABLE zz_write_log (table_name text NOT NULL, op text NOT NULL)")
        connection.execute(
            sql.SQL("GRANT INSERT ON zz_write_log TO {}").format(sql.Identifier(db.roles.runtime))
        )
        connection.execute(
            "CREATE FUNCTION zz_log_write() RETURNS trigger LANGUAGE plpgsql AS $$"
            " BEGIN INSERT INTO zz_write_log VALUES (TG_TABLE_NAME, TG_OP); RETURN NULL; END $$"
        )
        tables = [name for (name,) in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'zz_write_log'"
        )]
        for table in tables:
            connection.execute(
                sql.SQL(
                    "CREATE TRIGGER zz_write_log AFTER INSERT OR UPDATE OR DELETE ON {}"
                    " FOR EACH STATEMENT EXECUTE FUNCTION zz_log_write()"
                ).format(sql.Identifier(table))
            )
        connection.commit()
    return tables


def written(db, start_over=False):
    with connect(db.owner) as connection:
        rows = connection.execute("SELECT DISTINCT table_name FROM zz_write_log").fetchall()
        if start_over:
            connection.execute("DELETE FROM zz_write_log")
            connection.commit()
    return {name for (name,) in rows}


def test_connection_test_and_routing_write_only_mdl_audit_and_session_tables(m4):
    db = m4
    provider = local_provider(db)
    model = add_model(db, provider["id"])
    from .test_m3_mdl_api import call

    call(db, "PATCH", f"/models/{model['id']}", {"risk_level": "LOW"})
    tables = install_write_log(db)
    assert len(tables) > 20  # every table, including any future quota/credit table
    written(db, start_over=True)

    assert run_test(db, model["id"])["status"] == "PASSED"
    tested = written(db, start_over=True)
    assert tested <= {"mdl_connection_tests", "audit_events", "auth_sessions"}, tested
    assert {"mdl_connection_tests", "audit_events"} <= tested

    put(db, 0, model["id"])
    routed = written(db, start_over=True)
    assert routed <= {"mdl_routing", "mdl_routing_revisions", "audit_events", "auth_sessions"}, routed

    for path in ("/routing", f"/models/{model['id']}", "/models", "/status"):
        call(db, "GET", path)
    assert written(db) <= {"auth_sessions"}  # reads write nothing else

    everything = tested | routed
    assert not [name for name in everything if any(word in name for word in ("quota", "credit", "qta", "crt", "ledger", "balance"))]
