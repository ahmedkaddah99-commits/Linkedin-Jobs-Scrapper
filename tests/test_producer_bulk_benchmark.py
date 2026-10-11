from scripts.benchmark_producer_bulk_ingest import run_benchmark


def test_producer_bulk_benchmark_reports_throughput_and_bounded_calls(tmp_path):
    report = run_benchmark(
        output_dir=tmp_path,
        company_count=6,
        jobs_per_company=2,
    )

    assert report["schema_version"] == "runr.producer-bulk-benchmark.v1"
    assert report["workload"] == {"companies": 6, "jobs": 12, "jobs_per_company": 2}
    assert set(report["modes"]) == {"legacy", "bulk"}
    for result in report["modes"].values():
        assert result["companies_per_minute"] > 0
        assert result["jobs_per_minute"] > 0
        assert result["database"]["transactions"] > 0
        assert result["timing_seconds"]["normalization"] >= 0
        assert result["timing_seconds"]["reads"] >= 0
        assert result["timing_seconds"]["writes"] >= 0
        assert result["timing_seconds"]["commits"] >= 0

    assert report["modes"]["bulk"]["database"]["transactions"] < report["modes"]["legacy"]["database"]["transactions"]
    assert report["modes"]["bulk"]["database"]["statement_calls"] < report["modes"]["legacy"]["database"]["statement_calls"]
    assert report["comparison"]["statement_call_reduction_factor"] > 1
