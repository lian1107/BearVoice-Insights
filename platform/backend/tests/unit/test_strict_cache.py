import pytest

from bearvoice.modules.analysis.cache import CacheMiss, load_cached_json


def test_cache_only_loader_never_calls_a_model(tmp_path):
    with pytest.raises(CacheMiss, match="禁止补算"):
        load_cached_json("not-cached", "extract", build_dir=tmp_path)
