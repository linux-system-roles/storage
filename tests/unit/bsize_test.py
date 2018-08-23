import pytest

from size import Size

def test_bsize():
    # check failure on incorrect string
    with pytest.raises(ValueError) as e:
        Size("hugala buga lugala")
    assert "does not contain size" in str(e.value)

    # check failure on malformed units
    with pytest.raises(ValueError) as e:
        Size("1 GidB")
    assert "Unable to identify unit" in str(e.value)

    # accept int parameter, without units
    assert Size(0).get() == "0.0 B"

    # accept parameter with an exponent
    assert Size("1.048576e+06B").get() == "1.0 MiB"

    # accept units case insensitive, without space, convert
    assert Size("1000kilObytes").get("autodec", "%d") == "1"

    # check conversion from decimal to binary
    assert Size("1048.576 KB").get("mebibytes", "%0.5f %sb") == "1.00000 MiB"

    # check string to bytes conversion
    assert Size("1.2 terabyte").bytes == 1.2e12
