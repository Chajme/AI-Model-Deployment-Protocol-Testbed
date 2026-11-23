import csv
import json
import os

import pytest

import scripts.export_measurements as ex

EN_DASH = "–"


def write_run(base_dir, run_id, manifest, client_rows, kind):
    run_dir = os.path.join(base_dir, run_id)
    os.makedirs(os.path.join(run_dir, "pcap"), exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump({"run_id": run_id, **manifest}, fh)
    if client_rows:
        with open(os.path.join(run_dir, f"{kind}_measurements.csv"), "w",
                  newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(client_rows[0]))
            writer.writeheader()
            writer.writerows(client_rows)


def http_get_row(size_mb, seconds, ok=True):
    return {"protocol": "http-get", "direction": "download", "tls": "False",
            "file_size": size_mb, "time_to_transfer": seconds,
            "latency_tcp_rtt": "0.08", "tls_handshake_s": "X", "latency_ttfb": "0.2",
            "goodput_mbps": "1.0", "resumed": "0", "bytes_resumed": "0",
            "integrity_ok": str(ok), "avg_cpu_usage": "0.2%",
            "peak_ram_usage": "28.0 MB", "sample_count": "50"}


@pytest.fixture(autouse=True)
def reset_globals():
    ex.AGGREGATE = False
    ex.SIZE_ORDER = list(ex.DEFAULT_SIZES)
    yield
    ex.AGGREGATE = False
    ex.SIZE_ORDER = list(ex.DEFAULT_SIZES)


def test_size_label():
    assert ex.size_label(256000) == "250 KB"
    assert ex.size_label(1048576) == "1 MB"
    assert ex.size_label(2 * 1048576) == "2 MB"


def test_schema_of_variants():
    assert ex.schema_of("mqtt+tls") == "mqtt"
    assert ex.schema_of("mqtt-windowed") == "mqtt"
    assert ex.schema_of("http-get+tls") == "http-get"
    assert ex.schema_of("coap") == "coap"


def test_agg_text_single_value_is_verbatim():
    assert ex.agg_text(["1.570"]) == "1.570"
    assert ex.agg_text(["X"]) == ex.DASH


def test_agg_text_median_iqr():
    assert ex.agg_text(["1", "2", "3", "4", "5"]) == f"3 [2{EN_DASH}4]"


def test_agg_row_integrity_counts():
    rows = [http_get_row(1.0, "1.0"), http_get_row(1.0, "2.0", ok=False),
            http_get_row(1.0, "3.0")]
    out = ex.agg_row(rows)
    assert out["integrity_ok"] == "2/3"
    assert out["time_to_transfer"] == f"2 [1.5{EN_DASH}2.5]"
    assert out["protocol"] == "http-get"


def test_aggregate_cell_flags_small_n_and_failures():
    assert ex.aggregate_cell(["1", "2", "3", "4", "5"], ok=5, attempts=5) == \
        f"3 [2{EN_DASH}4] n=5 100%"
    assert ex.aggregate_cell(["1", "2", "3"], ok=3, attempts=3).endswith(ex.FLAG)
    assert ex.aggregate_cell(["1", "2", "3", "4", "5"], ok=4, attempts=5).endswith("80%" + ex.FLAG)
    assert ex.aggregate_cell([], ok=0, attempts=5) == "failed (0/5)"
    assert ex.aggregate_cell([], ok=0, attempts=0) == ex.DASH


def test_completeness_uses_manifest_sizes(tmp_path):
    rows = [http_get_row(0.244140625, "0.5"), http_get_row(1.0, "1.2")]
    write_run(tmp_path, "r1", {"protocol": "http-get", "network_profile": "nbiot",
                               "file_sizes": [256000, 1048576]}, rows, "http-get")
    (run,) = ex.load_runs(str(tmp_path))
    assert ex.sizes_covered(ex.client_rows(run)) == {256000, 1048576}
    assert ex.is_complete(run)            # not all five default sizes needed


def test_tls_runs_become_their_own_variant(tmp_path):
    write_run(tmp_path, "r1", {"protocol": "http-get", "network_profile": "good",
                               "tls": True, "file_sizes": [256000]},
              [http_get_row(0.244140625, "0.6")], "http-get")
    (run,) = ex.load_runs(str(tmp_path))
    assert run["protocol"] == "http-get+tls" and run["base"] == "http-get"


def test_sweep_aggregation_counts_attempts_and_successes(tmp_path):
    # Three repetitions; the third transfer crashed and wrote no row at all.
    for i, rows in enumerate([[http_get_row(1.0, "1.0")], [http_get_row(1.0, "2.0")], []], 1):
        write_run(tmp_path, f"r{i}", {"protocol": "http-get", "network_profile": "good",
                                      "sweep_id": "s1", "repeat_index": i,
                                      "file_sizes": [1048576]}, rows, "http-get")
    write_run(tmp_path, "other", {"protocol": "http-get", "network_profile": "good",
                                  "sweep_id": "s2", "file_sizes": [1048576]},
              [http_get_row(1.0, "9.0")], "http-get")
    runs = ex.load_runs(str(tmp_path))
    dataset = ex.collect_dataset(runs, ["http-get"], ["good"], cache={}, sweep_ids={"s1"})
    entry = dataset[("http-get", "good")]
    assert sorted(entry["run_ids"]) == ["r1", "r2", "r3"]
    assert entry["attempts"][(1048576, "")] == 3
    assert ex.successes(entry, "http-get", 1048576, "") == 2

    ex.AGGREGATE = True
    field = ex.make_client_field(ex.TRANSFER_FIELD)
    cell = ex.render_cell(dataset, "http-get", "good", "", 1048576, field, ex.cell_raw)
    assert cell == f"1.5 [1.25{EN_DASH}1.75] n=2 67%" + ex.FLAG


def test_newest_complete_run_is_picked_without_sweep(tmp_path):
    write_run(tmp_path, "20260101T000000_http-get_good", {"protocol": "http-get",
              "network_profile": "good", "file_sizes": [256000]},
              [http_get_row(0.244140625, "1.0")], "http-get")
    write_run(tmp_path, "20260102T000000_http-get_good", {"protocol": "http-get",
              "network_profile": "good", "file_sizes": [256000]}, [], "http-get")
    run, complete = ex.pick_canonical(ex.load_runs(str(tmp_path)), "http-get", "good")
    assert run["id"] == "20260101T000000_http-get_good" and complete
