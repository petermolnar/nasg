__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import unittest
import pandoc
import exiftool
import nasg
import os
import json

class TestNASG(unittest.TestCase):
    def test_url2slug(self):
        i = 'http://boffosocko.com/2017/10/28/content-bloat-privacy-archives-peter-molnar/'
        o = 'boffosockocom20171028content-bloat-privacy-archives-peter-molnar'
        self.assertEqual(nasg.url2slug(i), o)

class TestSingular(unittest.TestCase):
    singular = nasg.Singular('tests/index.md')

    # TODO: WTF?
    #def test_category(self):
        #print(self.singular.category)
        #self.assertEqual(self.singular.category, 'tests')

    #def test_files(self):

        #self.assertEqual(
            #self.singular.files,
            #['/home/pemolnar/Projects/petermolnar.net/nasg/tests/tests.jpg']

    def test_is_photo(self):
        self.assertTrue(self.singular.is_photo)

    def test_is_front(self):
        self.assertFalse(self.singular.is_front)

    def test_singular_tags(self):
        self.assertEqual(
            self.singular.tags,
            [
                'Llyn Idwal',
                'winter',
                'spring',
                'cloudy',
                'Snowdonia',
                'mountain',
                'clouds',
                'lake',
                'mountains',
                'snow',
                'Wales',
                'water'
            ]
        )

class TestExiftool(unittest.TestCase):
    def test_exiftool(self):
        if os.path.exists('tests/.Exif.tests.jpg.json'):
            os.unlink('tests/.Exif.tests.jpg.json')
        with open('tests/tests.jpg.json', 'rt') as expected:
            o = json.loads(expected.read())
        self.assertEqual(exiftool.Exif('tests/tests.jpg'), o)
        self.assertTrue(os.path.exists('tests/.Exif.tests.jpg.json'))
        self.assertTrue(
            os.path.getmtime('tests/.Exif.tests.jpg.json') >
            os.path.getmtime('tests/tests.jpg.json')
        )

class TestPandoc(unittest.TestCase):
    def test_pandoc(self):
        i = '_this_ is a **test** string for [pandoc](https://pandoc.org)'
        o = '<p><em>this</em> is a <strong>test</strong> string for <a href="https://pandoc.org">pandoc</a></p>'
        self.assertEqual(pandoc.Pandoc(i), o)


if __name__ == '__main__':
    unittest.main()
