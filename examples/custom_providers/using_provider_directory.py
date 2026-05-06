"""Example of using provider directories to load custom providers."""

import asyncio
from pathlib import Path

from proxybroker import Broker, create_provider_config_template


async def main():
    # Example 1: Load providers from a directory
    print("=== Loading providers from directory ===")

    # Create a custom providers directory
    custom_dir = Path("./my_custom_providers")
    custom_dir.mkdir(exist_ok=True)

    # Create some template configurations
    create_provider_config_template(
        custom_dir / "simple_proxy_list.yaml", provider_type="simple"
    )
    create_provider_config_template(
        custom_dir / "paginated_proxy_site.yaml", provider_type="paginated"
    )
    create_provider_config_template(custom_dir / "proxy_api.json", provider_type="api")

    print(f"Created template configurations in {custom_dir}")
    print("Edit these files with your actual proxy source URLs\n")

    # Example 2: Use provider directories with Broker
    print("=== Using custom provider directory with Broker ===")

    # Create broker with custom provider directory
    broker = Broker(
        provider_dirs=[str(custom_dir)],  # Load from custom directory
        providers=None,  # Don't use default providers
    )

    # You can also combine default providers with custom ones
    broker_combined = Broker(
        provider_dirs=[str(custom_dir)],  # Load from custom directory
        providers=None,  # None means use defaults + custom
    )

    # Example 3: Mix custom providers with code-defined ones
    print("=== Mixing configuration and code providers ===")

    from proxybroker import SimpleProvider

    # Define a provider in code
    code_provider = SimpleProvider(
        url="http://example.com/proxies.txt", format="text", proto=("HTTP", "HTTPS")
    )

    # Use both
    broker_mixed = Broker(
        providers=[code_provider],  # Code-defined providers
        provider_dirs=[str(custom_dir)],  # Plus directory providers
    )

    # Example 4: Multiple provider directories
    print("=== Using multiple provider directories ===")

    # You might have providers organized by type or source
    http_providers_dir = Path("./providers/http")
    socks_providers_dir = Path("./providers/socks")
    api_providers_dir = Path("./providers/apis")

    # Create directories
    for dir_path in [http_providers_dir, socks_providers_dir, api_providers_dir]:
        dir_path.mkdir(parents=True, exist_ok=True)

    # Load from all directories
    broker_multi = Broker(
        provider_dirs=[
            str(http_providers_dir),
            str(socks_providers_dir),
            str(api_providers_dir),
        ]
    )

    print(
        "\nProvider directories created. Add your provider configurations to use them!"
    )

    # Example 5: Demonstration with actual proxy finding
    # (This would work if you have actual provider configurations)
    """
    async for proxy in broker.find(types=['HTTP', 'HTTPS'], limit=10):
        print(f"Found proxy: {proxy.host}:{proxy.port}")
    """


if __name__ == "__main__":
    asyncio.run(main())
