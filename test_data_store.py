import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from data_store import data_directory


class DataStoreTests(unittest.TestCase):
    def test_local_location_and_environment_override(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'SCROLL_STUDIO_DATA':''}):
            root=Path(folder)
            self.assertEqual(data_directory(root),root/'data')
            target=root/'another-drive'/'画心数据'
            (root/'data-location.txt').write_text(str(target)+'\n','utf-8-sig')
            self.assertEqual(data_directory(root),target)
            with patch.dict(os.environ,{'SCROLL_STUDIO_DATA':str(root/'isolated-tests')}):
                self.assertEqual(data_directory(root),root/'isolated-tests')
            (root/'data-location.txt').write_text('relative-data','utf-8')
            self.assertEqual(data_directory(root),root/'relative-data')
            (root/'data-location.txt').write_text('  ','utf-8')
            with self.assertRaises(ValueError):data_directory(root)


if __name__=='__main__':unittest.main()
