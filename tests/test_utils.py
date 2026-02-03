from app.utils import is_valid_apple_music_url, sanitize_title


def test_valid_apple_music_urls():
    assert is_valid_apple_music_url('https://music.apple.com/us/album/123')
    assert is_valid_apple_music_url('http://music.apple.com/album/456')
    assert not is_valid_apple_music_url('https://example.com')
    assert not is_valid_apple_music_url('ftp://music.apple.com/album/1')


def test_sanitize_title():
    assert sanitize_title('  My Album  ') == 'My Album'
    long = 'x' * 500
    assert len(sanitize_title(long)) <= 200
