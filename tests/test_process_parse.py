from app.process_manager import DownloaderManager


SAMPLE_TABLE = [
    "| 1 | Artist - Album Title | 2021 | 12:34 | Album |",
    "| 2 | Another - Single Title | 2020 | 03:21 | Single |"
]

SAMPLE_LIST = [
    "1. Track One - Artist",
    "2. Track Two - Artist"
]


def test_parse_table_options():
    d = DownloaderManager()
    opts = d._parse_options(SAMPLE_TABLE)
    assert isinstance(opts, list)
    assert len(opts) >= 2
    assert opts[0]['id'] == '1'
    assert 'label' in opts[0]


def test_parse_list_options():
    d = DownloaderManager()
    opts = d._parse_options(SAMPLE_LIST)
    assert isinstance(opts, list)
    assert len(opts) >= 2
    assert opts[0]['id'] == '1'
    assert 'label' in opts[0]
