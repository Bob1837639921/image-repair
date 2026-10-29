"""Create a portable release containing program files only, never user data."""
import argparse
import os
from pathlib import Path
import zipfile


def main():
    parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('archive');args=parser.parse_args()
    folder=Path(args.folder);archive=Path(args.archive)
    files=[folder/'画心.exe',folder/'使用说明.txt']+sorted(p for p in (folder/'_internal').rglob('*') if p.is_file())
    temp=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as output:
        for path in files:output.write(path,Path('画心')/path.relative_to(folder))
    with zipfile.ZipFile(temp) as output:
        assert output.testzip() is None
        assert not any(p.startswith(('画心/data/','画心/logs/')) for p in output.namelist())
    os.replace(temp,archive)
    print(str(archive))

if __name__=='__main__':main()
