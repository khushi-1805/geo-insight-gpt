from pathlib import Path
from evacuation.flood_escape import run_flood_escape_analysis
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from flood.pipeline import run_flood_analysis
import json
import traceback
import threading
import queue

from llm.planner import understand_question
from llm.reporter import generate_report
from analysis_engine import run_analysis
from flood.routing import geocode_route_locations, calculate_route
from flood.corridor import create_route_corridor
from dotenv import load_dotenv

from flood.geocoding import geocode_location
load_dotenv()

import numpy as np

from flood.geocoding import geocode_location
from flood.routing import calculate_route
from flood.preprocessing import (
    load_flood_bands,
    get_flood_raster_metadata,
)
from flood.flood_detection import detect_flood
from flood.route_risk import calculate_route_risk
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from evacuation.pipeline import run_evacuation_analysis
# ============================================================
# FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="Geo-Insight GPT API"
)
class FloodEscapeRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    radius_m: float = Field(default=3000, gt=0)
    safety_offset_m: float = Field(default=500, gt=0)

    start_date: str | None = None
    end_date: str | None = None

    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    max_candidates: int = Field(default=5, ge=1, le=20)
class EvacuationSearchRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)

    radius_m: float = Field(default=3000, gt=0)
    min_area_m2: float = Field(default=10000, gt=0)

    start_date: str | None = None
    end_date: str | None = None

    max_cloud_cover: float = Field(default=20, ge=0, le=100)
    limit: int = Field(default=5, ge=1, le=20)

# ============================================================
# CORS
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
(STATIC_DIR / "overlays").mkdir(parents=True, exist_ok=True)

app.mount(
    "/static",
    StaticFiles(directory=str(STATIC_DIR)),
    name="static"
)


# ============================================================
# ROOT ENDPOINT
# ============================================================

@app.get("/")
def root():

    return {
        "message": "Geo-Insight GPT Backend Running"
    }


# ============================================================
# EMPTY RESULTS STRUCTURE
# ============================================================
#
# Used for general/casual questions.
#
# This prevents the frontend from crashing because it expects:
#
# results.analyses.vegetation
# results.analyses.water
# results.analyses.development
#
# ============================================================

def empty_results():

    return {
        "boundary": None,
        "analyses": {
            "vegetation": [],
            "water": [],
            "development": []
        }
    }

@app.get("/flood/analyze")
def analyze_flood_route(
    origin: str,
    destination: str,
):
    try:
        return run_flood_analysis(
            origin,
            destination,
        )

    except ValueError as error:
        print("FLOOD ERROR:", error)
        raise HTTPException(status_code=400, detail=str(error))

    except Exception as error:
        print("FLOOD ERROR:", error)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))

    except Exception as error:
        traceback.print_exc()

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )

@app.get("/flood/route-locations")
def flood_route_locations(query: str):
    try:
        locations = geocode_route_locations(query)

        route = calculate_route(
            locations["origin"],
            locations["destination"],
        )

        possible_route_area = create_route_corridor(
            route["routes"]
        )

        return {
            "success": True,
            "origin": locations["origin"],
            "destination": locations["destination"],
            "route": route,
            "possible_route_area": possible_route_area,
        }

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except Exception as error:
        print("\n===== FLOOD ROUTING ERROR =====")
        traceback.print_exc()
        print("===============================\n")

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )
@app.get("/flood/geocode")
def flood_geocode(query: str):

    try:

        result = geocode_location(query)

        return {
            "success": True,
            "location": result
        }

    except ValueError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error)
        )

    except Exception as error:

        print("\n===== GEOCODING ERROR =====")
        traceback.print_exc()
        print("===========================\n")

        raise HTTPException(
            status_code=500,
            detail=str(error)
        )
# ============================================================
# NORMAL ENDPOINT
# ============================================================

@app.post("/ask")
def ask_question(
    question: str
):

    try:

        # ====================================================
        # 1. UNDERSTAND QUESTION
        # ====================================================

        plan = understand_question(
            question
        )


        # ====================================================
        # 2. GENERAL / CASUAL QUESTION
        # ====================================================
        #
        # Examples:
        #
        # "What is NDVI?"
        # "Explain MNDWI"
        # "hi"
        # "hello"
        #
        # No satellite analysis is required.
        #
        # ====================================================

        if plan.get(
            "intent"
        ) in ["general", "casual"]:

            results = empty_results()

            report = generate_report(
                question,
                plan,
                results
            )

            return {
                "question": question,
                "plan": plan,
                "results": results,
                "report": report
            }


        # ====================================================
        # 3. ANALYSIS QUESTION
        # ====================================================
        #
        # Example:
        #
        # "How has vegetation changed in Bengaluru
        #  from 2020 to 2025?"
        #
        # Existing satellite-analysis pipeline is used.
        #
        # ====================================================

        results = run_analysis(
            plan
        )


        # ====================================================
        # 4. GENERATE AI REPORT
        # ====================================================

        report = generate_report(
            question,
            plan,
            results
        )


        # ====================================================
        # 5. RETURN RESULT
        # ====================================================

        return {
            "question": question,
            "plan": plan,
            "results": results,
            "report": report
        }


    except Exception as error:

        print(
            "\n===== ERROR ====="
        )

        traceback.print_exc()

        print(
            "=================\n"
        )


        raise HTTPException(
            status_code=500,
            detail=str(error)
        )


# ============================================================
# STREAMING ENDPOINT
# ============================================================
# ============================================================
# EVACUATION SEARCH ENDPOINT
# ============================================================

@app.post("/evacuation/search")
def search_evacuation_destinations(
    request: EvacuationSearchRequest
):
    try:
        result = run_evacuation_analysis(
            latitude=request.latitude,
            longitude=request.longitude,
            radius_m=request.radius_m,
            min_area_m2=request.min_area_m2,
            start_date=request.start_date,
            end_date=request.end_date,
            max_cloud_cover=request.max_cloud_cover,
            limit=request.limit,
        )

        return jsonable_encoder(result)

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:
        print("\n===== EVACUATION ERROR =====")
        traceback.print_exc()
        print("============================\n")

        raise HTTPException(
            status_code=500,
            detail=str(error),
        )
# ============================================================
# FLOOD ESCAPE ENDPOINT
# ============================================================

@app.post("/evacuation/escape")
def find_flood_escape(request: FloodEscapeRequest):
    try:
        result = run_flood_escape_analysis(
            latitude=request.latitude,
            longitude=request.longitude,
            radius_m=request.radius_m,
            safety_offset_m=request.safety_offset_m,
            start_date=request.start_date,
            end_date=request.end_date,
            max_cloud_cover=request.max_cloud_cover,
            max_candidates=request.max_candidates,
        )

        return jsonable_encoder(result)

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))

    except Exception as error:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(error))
    
@app.post("/ask/stream")
def ask_question_stream(
    question: str
):

    # --------------------------------------------------------
    # Queue used to transfer progress events from the
    # background analysis thread to the SSE response.
    # --------------------------------------------------------

    event_queue = queue.Queue()


    # --------------------------------------------------------
    # Sentinel value used to tell the streaming loop
    # that the background worker has finished.
    # --------------------------------------------------------

    DONE = object()


    # ========================================================
    # BACKGROUND WORKER
    # ========================================================

    def run_backend():

        try:

            # =================================================
            # 1. UNDERSTAND QUESTION
            # =================================================

            event_queue.put({
                "type": "status",
                "message":
                    "Understanding your geographic question..."
            })


            plan = understand_question(
                question
            )


            # =================================================
            # 2. GENERAL / CASUAL QUESTION
            # =================================================
            #
            # No satellite processing.
            #
            # =================================================

            if plan.get(
                "intent"
            ) in ["general", "casual"]:

                # ---------------------------------------------
                # Status message
                # ---------------------------------------------

                if plan.get(
                    "intent"
                ) == "casual":

                    event_queue.put({
                        "type": "status",
                        "message":
                            "Preparing response..."
                    })

                else:

                    event_queue.put({
                        "type": "status",
                        "message":
                            "Preparing explanation..."
                    })


                # ---------------------------------------------
                # Empty but valid results structure
                # ---------------------------------------------

                results = empty_results()


                # ---------------------------------------------
                # Generate response
                # ---------------------------------------------

                report = generate_report(
                    question,
                    plan,
                    results
                )


            # =================================================
            # 3. ANALYSIS QUESTION
            # =================================================
            #
            # Existing satellite-analysis pipeline.
            #
            # =================================================

            else:

                event_queue.put({
                    "type": "status",
                    "message":
                        "Starting satellite analysis..."
                })


                # =============================================
                # Progress callback
                # =============================================

                def progress_callback(
                    event_type,
                    message,
                    year=None,
                    analysis=None,
                    total=None,
                    completed=None
                ):

                    event_queue.put({
                        "type": event_type,
                        "message": message,
                        "year": year,
                        "analysis": analysis,
                        "total": total,
                        "completed": completed
                    })


                # =============================================
                # Run actual satellite analysis
                # =============================================

                results = run_analysis(
                    plan,
                    progress_callback=progress_callback
                )


                # =============================================
                # Generate report
                # =============================================

                event_queue.put({
                    "type": "status",
                    "message":
                        "Generating geographic report..."
                })


                report = generate_report(
                    question,
                    plan,
                    results
                )


            # =================================================
            # 4. FINAL RESULT
            # =================================================

            final_result = {
                "question": question,
                "plan": plan,
                "results": results,
                "report": report
            }


            event_queue.put({
                "type": "complete",
                "result": final_result
            })


        # =====================================================
        # ERROR HANDLING
        # =====================================================

        except Exception as error:

            print(
                "\n===== STREAMING ERROR ====="
            )

            traceback.print_exc()

            print(
                "===========================\n"
            )


            event_queue.put({
                "type": "error",
                "message": str(error)
            })


        finally:

            # ------------------------------------------------
            # Tell SSE stream that the worker is finished.
            # ------------------------------------------------

            event_queue.put(
                DONE
            )


    # ========================================================
    # START BACKGROUND PROCESSING
    # ========================================================

    worker = threading.Thread(
        target=run_backend,
        daemon=True
    )


    worker.start()


    # ========================================================
    # SSE GENERATOR
    # ========================================================

    def event_stream():

        while True:

            event = event_queue.get()


            # -----------------------------------------------
            # Background worker finished
            # -----------------------------------------------

            if event is DONE:

                break


            # -----------------------------------------------
            # Convert event to SSE format
            # -----------------------------------------------

            event_type = event.get(
                "type",
                "status"
            )


            data = {
                key: value
                for key, value in event.items()
                if key != "type"
            }


            yield (
                f"event: {event_type}\n"
                f"data: {json.dumps(data)}\n\n"
            )


    # ========================================================
    # RETURN LIVE SSE STREAM
    # ========================================================

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no-cache"
        }
    )