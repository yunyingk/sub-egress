import pytest
from app.builder import extract_dynamic_groups
from app.parsers.clash import detect_country


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("[SD] 🇺🇸 Australia-01", ("🇦🇺", "AU")),
        ("[SD] 🇺🇸 Russia-01", ("🇷🇺", "RU")),
        ("🇯🇵 美国-01", ("🇺🇸", "US")),
        ("🇺🇸 U.S. 01", ("🇺🇸", "US")),
        ("US-01", ("🇺🇸", "US")),
        ("🇺🇸 unknown-01", ("🇺🇸", "US")),
        ("unknown-01", ("🌐", "OTHER")),
        ("🇺🇸 Singapore-01", ("🇸🇬", "SG")),
        ("JP Australia-01", ("🇦🇺", "AU")),
    ],
)
def test_country_names_before_abbreviations_and_flags(name, expected):
    assert detect_country(name) == expected


def test_other_countries_do_not_enter_us_group():
    names = ["[SD] 🇺🇸 Australia-01", "[SD] 🇺🇸 Russia-01", "U.S. 01"]
    nodes = [{"name": name, "country_code": detect_country(name)[1]} for name in names]
    groups = extract_dynamic_groups(nodes)
    us_group = next(group for group in groups if group["country_code"] == "US")
    assert us_group["proxies"] == ["U.S. 01"]
