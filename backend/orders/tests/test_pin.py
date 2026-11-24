from django.contrib.gis.geos import Point


def test_order_pin_is_stored_as_a_postgis_point(place) -> None:
    order, _ = place()
    order.pin = Point(120.9842, 14.5995, srid=4326)
    order.save(update_fields=["pin"])

    order.refresh_from_db()

    assert order.pin is not None
    assert order.pin.srid == 4326
    assert order.pin.x == 120.9842
    assert order.pin.y == 14.5995
