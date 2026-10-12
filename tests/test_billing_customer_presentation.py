from backend.config.plans import get_plan, public_plan


def test_public_plan_excludes_provider_configuration(monkeypatch):
    monkeypatch.setenv("CREEM_RUNR_PRO_MONTHLY_PRODUCT_ID", "private-product")
    private = get_plan("runr_pro")
    public = public_plan(private)
    assert "creem_product_id" not in public
    assert all("creem_product_id" not in offer and "env_var" not in offer for offer in public["offers"])
    assert private["offers"][1]["creem_product_id"] == "private-product"
    assert public["offers"][1]["price"] == 39.99
