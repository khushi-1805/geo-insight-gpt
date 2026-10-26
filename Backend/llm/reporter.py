import os

from openai import OpenAI

from confidence import (
    LOW_CONFIDENCE_THRESHOLD,
    is_low_confidence,
)


# ============================================================
# OPENROUTER CLIENT
# ============================================================

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)


def _confidence_facts(satellite_results):
    """
    Extract real valid-pixel percentages from computed results.

    The LLM must explain these facts. It must not invent them.
    """

    analyses = (satellite_results or {}).get("analyses") or {}

    lines = []
    lowest = None
    any_low = False

    for name, yearly in analyses.items():

        if not isinstance(yearly, list):
            continue

        for row in yearly:

            if not isinstance(row, dict):
                continue

            if row.get("error"):
                continue

            percentage = row.get("valid_pixel_percentage")

            if percentage is None and row.get("valid_pixel_fraction") is not None:
                percentage = round(
                    float(row["valid_pixel_fraction"]) * 100.0,
                    2
                )

            if percentage is None:
                continue

            percentage = float(percentage)
            confidence = row.get("confidence") or "unknown"
            year = row.get("year")

            lines.append(
                f"- {name} {year}: "
                f"{percentage:.1f}% valid pixels "
                f"(confidence={confidence})"
            )

            if lowest is None or percentage < lowest:
                lowest = percentage

            if is_low_confidence(percentage):
                any_low = True

    return {
        "lines": lines,
        "lowest": lowest,
        "any_low": any_low
    }


# ============================================================
# REPORT GENERATOR
# ============================================================

def generate_report(
    question,
    plan,
    satellite_results
):

    # ========================================================
    # GENERAL QUESTION
    # ========================================================
    #
    # Examples:
    #
    # What is NDVI?
    # Explain MNDWI
    # What does NDBI mean?
    #
    # These questions do NOT have satellite results.
    # ========================================================

    if plan.get("intent") == "general":

        prompt = f"""
You are Geo-Insight GPT, a geographic and
remote-sensing assistant.

The user asked:

{question}

The question was classified as a GENERAL
EXPLANATION question.

Your job is to answer the user's question
clearly and accurately.

IMPORTANT RULES:

1. Answer the question directly.
2. Do NOT ask the user to provide years.
3. Do NOT ask the user to provide a location unless
   the question genuinely requires one.
4. Do NOT run or describe a satellite analysis as if
   one was performed.
5. Do NOT invent satellite-analysis results.
6. Explain technical concepts in simple language.
7. Use appropriate remote-sensing terminology.
8. If the user asks about an index such as NDVI,
   MNDWI, or NDBI, explain:
   - what it is
   - what it is used for
   - which Sentinel-2 bands are involved when relevant
   - how the value is interpreted
9. If explaining a formula, make the formula clear.
10. If the question is about Geo-Insight GPT itself,
    explain the relevant project functionality
    without inventing capabilities.

Keep the answer concise but useful.

Use headings when they improve readability.

Do NOT create a year-by-year analysis because
this is a general question.
"""

        # ====================================================
        # OPENROUTER REQUEST
        # ====================================================

        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )

        return response.choices[0].message.content


    # ========================================================
    # SATELLITE ANALYSIS QUESTION
    # ========================================================
    #
    # Existing report-generation behaviour.
    # ========================================================

    confidence = _confidence_facts(satellite_results)

    confidence_block = "\n".join(confidence["lines"]) or (
        "No valid-pixel percentages were supplied."
    )

    low_confidence_rule = ""

    if confidence["any_low"]:

        low_confidence_rule = f"""
14. LOW CONFIDENCE REQUIRED:
    At least one yearly result has fewer than
    {LOW_CONFIDENCE_THRESHOLD}% valid (non-masked) pixels.
    You MUST state clearly that those numbers are
    low-confidence because of cloud cover or limited
    valid satellite data. Do NOT present them as a
    clean, confident measurement.
"""

    else:

        low_confidence_rule = f"""
14. If every yearly result is at or above
    {LOW_CONFIDENCE_THRESHOLD}% valid pixels, you may
    treat the numbers as usable, but still mention
    valid-pixel coverage in the Important Note.
"""

    prompt = f"""
You are Geo-Insight GPT, a geographic analysis assistant.

The user asked:

{question}

The question was interpreted as:

{plan}

Below are REAL satellite-analysis results calculated
from Sentinel-2 imagery:

{satellite_results}

Valid-pixel / SCL-masking facts (computed, not estimated):

{confidence_block}

Your job is to explain these results clearly.

IMPORTANT RULES:

1. Use ONLY the supplied satellite results for
   numerical claims.

2. Do NOT invent values, dates, satellite images,
   or trends.

3. Explain NDVI, NDBI, MNDWI, vegetation coverage,
   built-up coverage, water coverage, or other
   relevant metrics when useful.

4. Compare the years provided in the data.

5. Mention the selected observation dates when relevant.

6. If the final year is incomplete, explicitly mention
   that.

7. Distinguish between:
   - vegetation coverage and average NDVI
   - built-up coverage and average NDBI
   - water coverage and average MNDWI

8. Explain major increases or decreases visible in
   the supplied data.

9. Do NOT claim that satellite data proves the cause
   of a change.

10. If the data is insufficient to answer part of
    the question, clearly say so.

11. Do not invent missing years.

12. Do not invent missing satellite observations.

13. Do not modify the numerical results supplied
    by the analysis engine.
{low_confidence_rule}
Give the answer in a clear report format:

## Summary

Brief overall finding.

## Year-by-Year Analysis

Explain the important changes across the years.

## Trend

Describe the overall trend using the supplied numbers.

## Important Note

Mention limitations such as observation dates,
partial years, cloud coverage, valid-pixel coverage,
or differences in satellite observations.

Keep the explanation understandable to a normal user,
but make it technically accurate.
"""

    # ========================================================
    # OPENROUTER REQUEST
    # ========================================================

    response = client.chat.completions.create(
        model="openrouter/free",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    return response.choices[0].message.content