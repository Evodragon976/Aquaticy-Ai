"""Vorbereitete GET-Antworten auch ueber die begrenzte HTTP-Stream-Schnittstelle pruefen."""

from contextlib import contextmanager


def get_stream(get):
    @contextmanager
    def stream(method, url, **kwargs):
        assert method == 'GET'
        response = get(url, **kwargs)
        try:
            yield response
        finally:
            response.close()

    return stream
