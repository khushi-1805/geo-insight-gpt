from openai import OpenAI
from dotenv import load_dotenv
import os
import json
from datetime import datetime

from pathlib import Path


# ============================================================
# ENVIRONMENT
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(
    BASE_DIR / ".env"
)


client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)


# ============================================================
# QUESTION UNDERSTANDING
# ============================================================

def understand_question(question):

    current_year = datetime.now().year

    prompt = f"""
You are the planning component of Geo-Insight GPT.

Your job is to understand the user's message and classify
it into ONE of THREE intents:

1. "general"
2. "analysis"
3. "casual"

============================================================
INTENT 1: GENERAL
============================================================

Use "general" when the user asks for an explanation,
definition, meaning, concept, formula, methodology, or
general geographic/remote-sensing information.

Examples:

"What is NDVI?"
"Can you explain NDVI?"
"What does NDVI mean?"
"Explain MNDWI"
"What is NDBI?"
"What is vegetation index?"
"How does NDVI work?"
"What bands are used for NDVI?"
"Explain how satellite vegetation analysis works"

These questions DO NOT require satellite processing.

For general questions:

- location = null
- analysis = []
- start_year = null
- end_year = null


============================================================
INTENT 2: ANALYSIS
============================================================

Use "analysis" when the user wants actual geographic,
historical, comparative, or satellite-based analysis.

Examples:

"How has vegetation changed in Bengaluru from 2020 to 2025?"

"How has water changed in Delhi from 2019 to 2025?"

"Analyze urbanisation in Mumbai between 2015 and 2025"

"Compare vegetation in Bengaluru from 2020 to 2026"

"How has Bengaluru changed from 2015 to 2025?"

These questions require geographic analysis.

If the user asks for historical/change/trend analysis
but does NOT provide a time period, keep:

start_year = null
end_year = null

Do NOT invent years.


============================================================
INTENT 3: CASUAL
============================================================

Use "casual" for greetings, simple conversational messages,
thanks, acknowledgements, or messages that do not ask for
geographic analysis or an explanation.

Examples:

"hi"
"hello"
"hey"
"hi there"
"good morning"
"good evening"
"thanks"
"thank you"
"okay"
"ok"
"cool"
"great"
"bye"
"goodbye"

These messages MUST NOT trigger satellite analysis.

For casual messages:

- location = null
- analysis = []
- start_year = null
- end_year = null


============================================================
IMPORTANT CLASSIFICATION RULE
============================================================

Do NOT classify every message as an analysis question.

Use:

"general"
→ when the user wants to LEARN or UNDERSTAND something.

"analysis"
→ when the user wants ACTUAL GEOGRAPHIC DATA,
historical comparison, change detection, trends, or
satellite analysis.

"casual"
→ when the user is simply TALKING, GREETING, THANKING,
ACKNOWLEDGING, or ENDING the conversation.


============================================================
LOCATION
============================================================

For analysis questions:

- Extract the geographic location mentioned by the user.
- It can be ANY city, district, state, country, region, etc.
- Do not assume Bengaluru or any other specific location.

For general questions:

- location MUST be null.

For casual messages:

- location MUST be null.


============================================================
ANALYSIS TYPES
============================================================

Possible analysis types:

- vegetation
- development
- water
- agriculture
- disaster
- environment
- complete_report

Rules:

Vegetation questions
→ ["vegetation"]

Development / urbanization questions
→ ["development"]

Water questions
→ ["water"]

Agriculture / crop questions
→ ["agriculture"]

Disaster questions
→ ["disaster"]

General environmental analysis questions
→ ["environment"]

Broad questions such as:

"How has Mumbai changed?"

→ ["complete_report"]

For GENERAL questions:
→ []

For CASUAL messages:
→ []


============================================================
YEARS
============================================================

Only extract years when the user provides or implies
a time period.

1. "from 2010 to 2020"

→ start_year = 2010
→ end_year = 2020


2. "between 2015 and 2023"

→ start_year = 2015
→ end_year = 2023


3. "since 2015"

→ start_year = 2015
→ end_year = {current_year}


4. "in the last 5 years"

→ start_year = {current_year - 5}
→ end_year = {current_year}


5. "over the past 10 years"

→ start_year = {current_year - 10}
→ end_year = {current_year}


6. If the user explicitly provides years,
ALWAYS use those exact years.


7. If the user does not mention a time period:

→ start_year = null
→ end_year = null


Do NOT assume 2020 or 2026.

For GENERAL and CASUAL messages:

→ start_year = null
→ end_year = null


============================================================
EXAMPLES
============================================================

User:
"hi"

Output:

{{
    "intent": "casual",
    "location": null,
    "analysis": [],
    "start_year": null,
    "end_year": null
}}


User:
"What is NDVI?"

Output:

{{
    "intent": "general",
    "location": null,
    "analysis": [],
    "start_year": null,
    "end_year": null
}}


User:
"How has vegetation changed in Bengaluru?"

Output:

{{
    "intent": "analysis",
    "location": "Bengaluru",
    "analysis": ["vegetation"],
    "start_year": null,
    "end_year": null
}}


User:
"How has vegetation changed in Bengaluru from 2020 to 2025?"

Output:

{{
    "intent": "analysis",
    "location": "Bengaluru",
    "analysis": ["vegetation"],
    "start_year": 2020,
    "end_year": 2025
}}


User:
"Thanks"

Output:

{{
    "intent": "casual",
    "location": null,
    "analysis": [],
    "start_year": null,
    "end_year": null
}}


============================================================
CURRENT YEAR
============================================================

Current year: {current_year}


============================================================
USER MESSAGE
============================================================

{question}


============================================================
OUTPUT
============================================================

Return ONLY valid JSON.

Use exactly this structure:

{{
    "intent": "general",
    "location": null,
    "analysis": [],
    "start_year": null,
    "end_year": null
}}

Do not include markdown.
Do not include explanations outside JSON.
"""


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


    result = response.choices[0].message.content.strip()

    # ========================================================
    # REMOVE MARKDOWN CODE FENCES
    # ========================================================

    if result.startswith("```"):

        result = result.replace(
            "```json",
            ""
        )

        result = result.replace(
            "```",
            ""
        )

        result = result.strip()


    # ========================================================
    # PARSE JSON
    # ========================================================

    plan = json.loads(
        result
    )


    # ========================================================
    # SAFETY DEFAULTS
    # ========================================================

    if "intent" not in plan:

        plan["intent"] = "casual"


    if "location" not in plan:

        plan["location"] = None


    if "analysis" not in plan:

        plan["analysis"] = []


    if "start_year" not in plan:

        plan["start_year"] = None


    if "end_year" not in plan:

        plan["end_year"] = None


    # ========================================================
    # NORMALIZE GENERAL
    # ========================================================

    if plan["intent"] == "general":

        plan["location"] = None

        plan["analysis"] = []

        plan["start_year"] = None

        plan["end_year"] = None


    # ========================================================
    # NORMALIZE CASUAL
    # ========================================================

    elif plan["intent"] == "casual":

        plan["location"] = None

        plan["analysis"] = []

        plan["start_year"] = None

        plan["end_year"] = None


    # ========================================================
    # SAFETY: UNKNOWN INTENT
    # ========================================================

    elif plan["intent"] not in [
        "general",
        "analysis",
        "casual"
    ]:

        plan["intent"] = "casual"

        plan["location"] = None

        plan["analysis"] = []

        plan["start_year"] = None

        plan["end_year"] = None


    return plan