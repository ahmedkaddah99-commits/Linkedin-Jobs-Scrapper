from pathlib import Path


def test_controller_is_self_contained_installable_package() -> None:
    product_root = Path(__file__).parents[2] / "runr_automation"

    assert (product_root / "pyproject.toml").is_file()
    assert (product_root / "src" / "runr_automation" / "cli.py").is_file()
    assert (product_root / "config" / "runr-automation.example.yaml").is_file()
    assert (product_root / "scripts").is_dir()
    assert (product_root / "skills").is_dir()
