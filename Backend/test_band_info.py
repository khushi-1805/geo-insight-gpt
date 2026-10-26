import rasterio
import os


bands = [
    "B02",
    "B03",
    "B04",
    "B8A",
    "B11",
    "B12",
]


for band in bands:

    path = os.path.join(
        "flood_data",
        f"{band}.tif"
    )

    with rasterio.open(path) as src:

        print("\n====================")
        print("Band:", band)
        print("Size:", src.width, "x", src.height)
        print("CRS:", src.crs)
        print("Resolution:", src.res)
        print("Data type:", src.dtypes[0])
        print("NoData:", src.nodata)
        print("====================")