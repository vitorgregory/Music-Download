from pathlib import Path
from app.process_manager import DownloaderManager, WrapperManager, get_wrapper_bin_path, get_wrapper_cache_dir, get_wrapper_rootfs_path


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


def test_wrapper_detects_2fa_prompt_variants():
    class FakeStdout:
        def __init__(self, lines):
            self._lines = iter(lines)

        def readline(self):
            return next(self._lines, '')

    class FakeProcess:
        def __init__(self, lines):
            self.stdout = FakeStdout(lines)
            self.stdin = type('FakeStdin', (), {'write': lambda self, *args, **kwargs: None, 'flush': lambda self: None})()
            self._poll = None

        def poll(self):
            return self._poll

    wrapper = WrapperManager()
    wrapper.process = FakeProcess([
        'CredentialHandler: authentication required',
        'Please enter the 2FA code to continue',
        ''
    ])

    wrapper._stream_logs()

    assert wrapper.needs_2fa is True


def test_wrapper_detects_2fa_flag_from_credential_handler():
    class FakeStdout:
        def __init__(self, lines):
            self._lines = iter(lines)

        def readline(self):
            return next(self._lines, '')

    class FakeProcess:
        def __init__(self, lines):
            self.stdout = FakeStdout(lines)
            self.stdin = type('FakeStdin', (), {'write': lambda self, *args, **kwargs: None, 'flush': lambda self: None})()
            self._poll = None

        def poll(self):
            return self._poll

    wrapper = WrapperManager()
    wrapper.process = FakeProcess([
        'credentialHandler: {title: , message: , 2FA: true}',
        ''
    ])

    wrapper._stream_logs()

    assert wrapper.needs_2fa is True


def test_downloader_detects_alternative_selection_prompt():
    class FakeStdout:
        def __init__(self, lines):
            self._lines = iter(lines)

        def readline(self):
            return next(self._lines, '')

    class FakeProcess:
        def __init__(self, lines):
            self.stdout = FakeStdout(lines)
            self.stdin = type('FakeStdin', (), {'write': lambda self, *args, **kwargs: None, 'flush': lambda self: None})()
            self._poll = None

        def poll(self):
            return self._poll

    downloader = DownloaderManager()
    downloader.process = FakeProcess([
        'Select one option from the list below:',
        '1) Track One - Artist',
        '2) Track Two - Artist',
        ''
    ])

    downloader._stream_logs()

    assert downloader.needs_input is True
    assert len(downloader.input_options) >= 2
    assert downloader.input_options[0]['id'] == '1'


def test_wrapper_paths_use_environment(monkeypatch, tmp_path):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    wrapper_bin = bindir / 'wrapper'
    wrapper_bin.write_text('#!/bin/sh\n')
    rootfs = tmp_path / 'rootfs'
    rootfs.mkdir()
    cache = tmp_path / 'cache' / 'wrapper'

    monkeypatch.setenv('WRAPPER_BIN', str(wrapper_bin))
    monkeypatch.setenv('WRAPPER_ROOTFS', str(rootfs))
    monkeypatch.setenv('WRAPPER_CACHE_DIR', str(cache))

    assert get_wrapper_bin_path() == wrapper_bin.resolve()
    assert get_wrapper_rootfs_path() == rootfs.resolve()
    assert get_wrapper_cache_dir() == cache.resolve()
    assert get_wrapper_cache_dir().exists()
