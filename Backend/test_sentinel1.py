import pystac_client
import planetary_computer

STAC_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

catalog = pystac_client.Client.open(
    STAC_URL,
    modifier=planetary_computer.sign_inplace,
)

search = catalog.search(
    collections=["sentinel-1-rtc"],
    bbox=[85.0, 27.8, 85.5, 28.2],
    datetime="2026-08-01/2026-09-11",
)

items = list(search.items())

print("Sentinel-1 RTC scenes found:", len(items))

for item in items[:5]:
    print("\nID:", item.id)
    print("Date:", item.datetime)

    print("Assets:")
    for name in item.assets:
        print("  ", name)