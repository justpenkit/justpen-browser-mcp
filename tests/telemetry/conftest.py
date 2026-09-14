import pytest

from .harness import Collector


@pytest.fixture
def collector(request):
    receiver = Collector(getattr(request, "param", "http/protobuf"))
    try:
        yield receiver
    finally:
        receiver.close()
