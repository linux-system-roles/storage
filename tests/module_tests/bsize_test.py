import six
import unittest
from bsize import Size

class SizeTestCase(unittest.TestCase):

    def test_size(self):
        # check failure on incorrect string
        with six.assertRaisesRegex(self, ValueError, "does not contain size"):
            Size("hugala buga lugala")

        # check failure on malformed units
        with six.assertRaisesRegex(self, ValueError, "Unable to identify unit"):
            Size("1 GidB")

        # accept int parameter, without units
        self.assertEqual(Size(0).get(), "0.0 B")

        # accept parameter with an exponent
        self.assertEqual(Size("1.048576e+06B").get(), "1.0 MiB")

        # accept units case insensitive, without space, convert
        self.assertEqual(Size("1000kilObytes").get("autodec", "%d"), "1")

        # check conversion from decimal to binary 
        self.assertEqual(Size("1048.576 KB").get("mebibytes", "%0.5f %sb"), "1.00000 MiB")

        # check string to bytes conversion
        self.assertEqual(Size("1.2 terabyte").bytes, 1.2e12)

