"""Catalog sync + pricing + curation-preservation tests."""

from app.catalog.sync_catalog import sync_catalog
from app.core.models import Category, Product
from app.providers.dummy import DummyProvider


def test_sync_inserts_catalog(db):
    sync_catalog(DummyProvider())
    assert db.query(Category).count() == 2
    assert db.query(Product).count() == 3


def test_sync_applies_margin(db):
    sync_catalog(DummyProvider())
    product = db.query(Product).filter_by(external_id=1).first()
    assert product.cost_price == 0.92
    assert product.price == round(0.92 * 1.2, 4)
    assert product.status == "active"

    # unavailable provider product -> inactive, but NOT deleted
    off = db.query(Product).filter_by(external_id=3).first()
    assert off.status == "inactive"


def test_sync_preserves_curation_and_override(db):
    """Sync must not resurrect hidden items nor clobber manual prices."""
    sync_catalog(DummyProvider())

    product = db.query(Product).filter_by(external_id=2).first()
    product.status = "inactive"
    product.price = 9.99
    product.price_override = True
    product.display_name = "UC محسّن"
    db.commit()

    # second sync with the same data (no changes upstream)
    sync_catalog(DummyProvider())
    db.expire_all()
    product = db.query(Product).filter_by(external_id=2).first()
    assert product.status == "inactive"        # curation kept
    assert product.price == 9.99               # override kept
    assert product.display_name == "UC محسّن"  # display kept

    # non-overridden product gets fresh margin
    other = db.query(Product).filter_by(external_id=1).first()
    assert other.price == round(0.92 * 1.2, 4)


def test_sync_fresh_deactivates_stale(db):
    sync_catalog(DummyProvider())
    # remove a product upstream, then sync with fresh
    provider = DummyProvider()
    del provider._products[3]
    sync_catalog(provider, fresh=True)
    db.expire_all()
    stale = db.query(Product).filter_by(external_id=3).first()
    assert stale is not None
    assert stale.status == "inactive"