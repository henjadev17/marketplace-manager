import pytest

from app.config import DEFAULT_TEMPLATE
from app.data.database import Database
from app.services.template_service import normalize_newlines, render_template


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r", "\u2028", "\u2029"])
def test_template_rendering_preserves_real_newlines(separator):
    template = separator.join(["{NOMBRE_PRODUCTO}", "", "{DESCRIPCION}", "{PRECIO}", "{METODO_ENTREGA}", "{FORMA_PAGO}", "{CONTACTO}"])
    result = render_template(template, "Monitor", "First\nSecond", 125.5, "Pickup", "Cash", "123")
    assert result == "Monitor\n\nFirst\nSecond\nS/ 125.50\nPickup\nCash\n123"
    assert "\\n" not in result
    assert normalize_newlines(result) == result


def test_template_storage_preserves_newlines_on_create_update_reopen(db):
    body = "{NOMBRE_PRODUCTO}\n\n{DESCRIPCION}\n"
    template_id = db.create_template("Multiline", body)
    assert db.get_template(template_id)["body"] == body
    updated = body + "\nContact\n"
    db.update_template(template_id, "Updated", updated)
    assert Database(db.db_path).get_template(template_id)["body"] == updated


def test_fresh_defaults_and_reopening_preserve_custom_values(db):
    templates = db.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "General"
    assert templates[0]["body"] == DEFAULT_TEMPLATE
    assert db.get_default_template_id() == db.get_last_template_id() == templates[0]["id"]
    assert db.get_defaults() == dict(category="", location="", status="DRAFT",
                                     delivery_method="", payment_method="", contact_number="")
    custom = dict(category="Electronics", location="Lima", status="READY",
                  delivery_method="Pickup\nDelivery", payment_method="Cash", contact_number="123")
    db.save_defaults(custom)
    reopened = Database(db.db_path)
    assert reopened.get_defaults() == custom
    assert reopened.list_templates() == templates
    assert reopened.get_template_settings()["delivery_method"] == custom["delivery_method"]


def test_template_deletion_fallback_and_last_template_guard(db):
    first = db.get_default_template_id()
    second = db.create_template("Second", "Text")
    db.set_default_template_id(second)
    db.set_last_template_id(second)
    db.delete_template(second)
    assert db.get_default_template_id() == db.get_last_template_id() == first
    db.set_setting("default_template_id", "invalid")
    db.set_setting("last_template_id", "999999")
    assert db.get_default_template_id() == db.get_last_template_id() == first
    with pytest.raises(ValueError):
        db.delete_template(first)
