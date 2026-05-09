"""Tests for custom provider examples."""

from examples.custom_providers.advanced_provider_example import AdvancedProvider


def test_advanced_provider_html_table_parser_handles_simple_rows():
    provider = AdvancedProvider()
    page = """
    <table>
      <tr class="proxy"><td>192.0.2.1</td><td>8080</td></tr>
      <tr><td>198.51.100.1</td><td>3128</td></tr>
      <TR><TD>203.0.113.1</TD><TD>8888</TD></TR>
      <tr><td>999.999.999.999</td><td>1234</td></tr>
      <tr><td>192.0.2</td><td>1234</td></tr>
      <tr><td>192.0.2.256</td><td>1234</td></tr>
      <tr><td>192.0.2.2</td><td>99999</td></tr>
      <tr><td>192.0.2.3</td><td>0</td></tr>
      <tr><td>192.0.2.4</td><td>-1</td></tr>
      <tr><td>192.0.2.5</td><td>http</td></tr>
    </table>
    """

    assert provider.find_proxies(page) == [
        ("192.0.2.1", "8080"),
        ("198.51.100.1", "3128"),
        ("203.0.113.1", "8888"),
    ]


def test_advanced_provider_json_helpers_skip_malformed_entries():
    provider = AdvancedProvider()

    assert provider.find_proxies(
        """
        {
          "proxies": [
            {"ip": "192.0.2.1", "port": 8080},
            {"ip": "198.51.100.1"},
            "203.0.113.1:8888"
          ]
        }
        """
    ) == [("192.0.2.1", "8080")]

    assert provider.find_proxies(
        """
        {
          "data": [
            "192.0.2.1:8080",
            {"ip": "198.51.100.1"}
          ]
        }
        """
    ) == [("192.0.2.1", "8080")]
