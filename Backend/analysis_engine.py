from location import get_coordinates

from analysis.vegetation import (
    calculate_yearly_vegetation
)

from analysis.urbanisation import (
    calculate_yearly_urbanisation
)

from analysis.water import (
    calculate_yearly_water
)


def run_analysis(
    plan,
    progress_callback=None
):

    location_name = plan["location"]
    analysis_types = plan["analysis"]

    start_year = plan.get("start_year")
    end_year = plan.get("end_year")

    if start_year is None or end_year is None:
        raise ValueError(
            "Please specify a time period, for example "
            "'from 2015 to 2025' or 'in the last 5 years'."
        )

    # ==========================================================
    # PROGRESS HELPER
    # ==========================================================

    def send_progress(
        event_type,
        message,
        year=None,
        analysis=None,
        total=None,
        completed=None
    ):

        if progress_callback is not None:

            progress_callback(
                event_type=event_type,
                message=message,
                year=year,
                analysis=analysis,
                total=total,
                completed=completed
            )

    # ==========================================================
    # LOCATION
    # ==========================================================

    send_progress(
        event_type="status",
        message="Identifying exact location boundary..."
    )

    location = get_coordinates(
        location_name
    )

    latitude = location["latitude"]
    longitude = location["longitude"]
    geometry = location["geometry"]

    # ==========================================================
    # RESULTS
    # ==========================================================

    results = {
        "location": location_name,

        "coordinates": {
            "latitude": latitude,
            "longitude": longitude
        },

        "period": {
            "start_year": start_year,
            "end_year": end_year
        },

        "boundary": {
            "type": "Feature",
            "properties": {
                "name": location_name
            },
            "geometry": geometry
        },

        "analyses": {}
    }

    # ==========================================================
    # DETERMINE TOTAL ANALYSES
    # ==========================================================

    number_of_years = (
        end_year - start_year + 1
    )

    total_analyses = 0

    if "vegetation" in analysis_types:
        total_analyses += number_of_years

    if "urbanisation" in analysis_types:
        total_analyses += number_of_years

    if "water" in analysis_types:
        total_analyses += number_of_years

    completed_analyses = 0

    # ==========================================================
    # VEGETATION
    # ==========================================================

    if "vegetation" in analysis_types:

        send_progress(
            event_type="status",
            message="Starting vegetation analysis..."
        )

        vegetation_results = []

        for year in range(
            start_year,
            end_year + 1
        ):

            send_progress(
                event_type="analysis_start",
                message=(
                    f"{year} vegetation analysis..."
                ),
                year=year,
                analysis="vegetation",
                total=total_analyses,
                completed=completed_analyses
            )

            try:

                result = calculate_yearly_vegetation(
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    year=year
                )

                vegetation_results.append(
                    result
                )

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} vegetation analysis"
                    ),
                    year=year,
                    analysis="vegetation",
                    total=total_analyses,
                    completed=completed_analyses
                )

            except Exception as error:

                vegetation_results.append({
                    "year": year,
                    "error": str(error)
                })

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} vegetation analysis "
                        f"(completed with error)"
                    ),
                    year=year,
                    analysis="vegetation",
                    total=total_analyses,
                    completed=completed_analyses
                )

        results[
            "analyses"
        ][
            "vegetation"
        ] = vegetation_results

    # ==========================================================
    # URBANISATION
    # ==========================================================

    if "urbanisation" in analysis_types:

        send_progress(
            event_type="status",
            message="Starting urbanisation analysis..."
        )

        urbanisation_results = []

        for year in range(
            start_year,
            end_year + 1
        ):

            send_progress(
                event_type="analysis_start",
                message=(
                    f"{year} urbanisation analysis..."
                ),
                year=year,
                analysis="urbanisation",
                total=total_analyses,
                completed=completed_analyses
            )

            try:

                result = calculate_yearly_urbanisation(
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    year=year
                )

                urbanisation_results.append(
                    result
                )

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} urbanisation analysis"
                    ),
                    year=year,
                    analysis="urbanisation",
                    total=total_analyses,
                    completed=completed_analyses
                )

            except Exception as error:

                urbanisation_results.append({
                    "year": year,
                    "error": str(error)
                })

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} urbanisation analysis "
                        f"(completed with error)"
                    ),
                    year=year,
                    analysis="urbanisation",
                    total=total_analyses,
                    completed=completed_analyses
                )

        results[
            "analyses"
        ][
            "urbanisation"
        ] = urbanisation_results

    # ==========================================================
    # WATER
    # ==========================================================

    if "water" in analysis_types:

        send_progress(
            event_type="status",
            message="Starting water analysis..."
        )

        water_results = []

        for year in range(
            start_year,
            end_year + 1
        ):

            send_progress(
                event_type="analysis_start",
                message=(
                    f"{year} water analysis..."
                ),
                year=year,
                analysis="water",
                total=total_analyses,
                completed=completed_analyses
            )

            try:

                result = calculate_yearly_water(
                    latitude=latitude,
                    longitude=longitude,
                    geometry=geometry,
                    year=year
                )

                water_results.append(
                    result
                )

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} water analysis"
                    ),
                    year=year,
                    analysis="water",
                    total=total_analyses,
                    completed=completed_analyses
                )

            except Exception as error:

                water_results.append({
                    "year": year,
                    "error": str(error)
                })

                completed_analyses += 1

                send_progress(
                    event_type="analysis_complete",
                    message=(
                        f"{year} water analysis "
                        f"(completed with error)"
                    ),
                    year=year,
                    analysis="water",
                    total=total_analyses,
                    completed=completed_analyses
                )

        results[
            "analyses"
        ][
            "water"
        ] = water_results

    # ==========================================================
    # AGRICULTURE
    # ==========================================================

    # ==========================================================
    # ALL ANALYSIS COMPLETE
    # ==========================================================

    send_progress(
        event_type="status",
        message="Satellite analysis completed.",
        total=total_analyses,
        completed=completed_analyses
    )

    return results