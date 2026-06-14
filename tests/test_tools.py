from tools import search_listings

def test_search_returns_results():
    results = search_listings("vintage graphic tee", size=None, max_price=50)
    assert isinstance(results, list) and len(results) > 0

def test_search_empty_results():
    results = search_listings("designer ballgown", size="XXS", max_price=5)
    assert results == []

def test_search_price_filter():
    results = search_listings("jacket", size=None, max_price=25)
    assert all(item["price"] <= 25 for item in results)

def test_search_size_filter():
    results = search_listings("tee", size="M", max_price=None)
    assert all("m" in str(item["size"]).lower() for item in results)